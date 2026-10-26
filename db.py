"""Работа с базой: SQLite локально, PostgreSQL на сервере. Код один и тот же благодаря SQLAlchemy."""

import asyncio
from datetime import date, datetime, timedelta

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, and_, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

import config
from slots import now_local


class Base(DeclarativeBase):
    pass


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    client_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    service_code: Mapped[str] = mapped_column(String(20))
    service_title: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(Integer)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)


def _build_engine():
    url = make_url(config.DATABASE_URL)
    connect_args = {}

    # Строку от Neon/Render вида postgresql://... переводим на асинхронный драйвер asyncpg
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+asyncpg")
    if url.drivername == "postgresql+asyncpg":
        # asyncpg не понимает sslmode/channel_binding из строки подключения, SSL включаем сами
        query = dict(url.query)
        sslmode = query.pop("sslmode", None)
        query.pop("channel_binding", None)
        url = url.set(query=query)
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = "require"

    return create_async_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = _build_engine()
Session = async_sessionmaker(engine, expire_on_commit=False)

# Бот работает в одном процессе, поэтому замка хватает, чтобы два клиента не заняли одно время
_booking_lock = asyncio.Lock()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _overlap(start: datetime, end: datetime):
    return and_(Booking.is_active.is_(True), Booking.start_at < end, Booking.end_at > start)


async def busy_intervals(day: date) -> list[tuple[datetime, datetime]]:
    day_start = datetime.combine(day, datetime.min.time())
    async with Session() as session:
        rows = await session.execute(
            select(Booking.start_at, Booking.end_at).where(_overlap(day_start, day_start + timedelta(days=1)))
        )
        return [(row.start_at, row.end_at) for row in rows]


async def create_booking(
    user_id: int, client_name: str, phone: str, service: config.Service, start_at: datetime
) -> Booking | None:
    """Создаёт запись. Возвращает None, если время успели занять, пока клиент выбирал."""
    end_at = start_at + timedelta(minutes=service.minutes)
    async with _booking_lock, Session() as session, session.begin():
        taken = await session.scalar(select(Booking.id).where(_overlap(start_at, end_at)).limit(1))
        if taken:
            return None
        booking = Booking(
            user_id=user_id,
            client_name=client_name,
            phone=phone,
            service_code=service.code,
            service_title=service.title,
            price=service.price,
            start_at=start_at,
            end_at=end_at,
            # Если до записи меньше суток, напоминание не нужно: клиент только что записался
            reminded=start_at - now_local() <= timedelta(hours=config.REMIND_BEFORE_HOURS),
        )
        session.add(booking)
    return booking


async def user_bookings(user_id: int) -> list[Booking]:
    async with Session() as session:
        result = await session.scalars(
            select(Booking)
            .where(Booking.user_id == user_id, Booking.is_active.is_(True), Booking.start_at >= now_local())
            .order_by(Booking.start_at)
        )
        return list(result)


async def last_phone(user_id: int) -> str | None:
    """Телефон из прошлой записи, чтобы постоянного клиента не спрашивать каждый раз."""
    async with Session() as session:
        return await session.scalar(
            select(Booking.phone).where(Booking.user_id == user_id).order_by(Booking.id.desc()).limit(1)
        )


async def day_bookings(day: date) -> list[Booking]:
    day_start = datetime.combine(day, datetime.min.time())
    async with Session() as session:
        result = await session.scalars(
            select(Booking)
            .where(_overlap(day_start, day_start + timedelta(days=1)))
            .order_by(Booking.start_at)
        )
        return list(result)


async def get_booking(booking_id: int) -> Booking | None:
    async with Session() as session:
        return await session.get(Booking, booking_id)


async def cancel_booking(booking_id: int) -> Booking | None:
    async with Session() as session, session.begin():
        booking = await session.get(Booking, booking_id)
        if not booking or not booking.is_active:
            return None
        booking.is_active = False
    return booking


async def due_reminders() -> list[Booking]:
    now = now_local()
    async with Session() as session:
        result = await session.scalars(
            select(Booking).where(
                Booking.is_active.is_(True),
                Booking.reminded.is_(False),
                Booking.start_at > now,
                Booking.start_at <= now + timedelta(hours=config.REMIND_BEFORE_HOURS),
            )
        )
        return list(result)


async def mark_reminded(booking_id: int) -> None:
    async with Session() as session, session.begin():
        booking = await session.get(Booking, booking_id)
        if booking:
            booking.reminded = True
