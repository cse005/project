import logging

from django.db import transaction
from django.db.models import Q

from kisan1.models import (
    BookingStatus,
    LaborBooking,
    Order,
    TractorBooking,
)

ACTIVE_BOOKING_STATES = [BookingStatus.PENDING, BookingStatus.CONFIRMED]
logger = logging.getLogger(__name__)


def create_order_record(*, farmer, provider, service_type, details, booking_date=None, hours=None, rate=0, total_amount=0):
    return Order.objects.create(
        user=farmer,
        provider=provider,
        service_type=service_type,
        details=details,
        booking_date=booking_date,
        hours=hours,
        rate=rate,
        total_amount=total_amount,
        farmer_mobile=farmer.mobile,
        status=BookingStatus.PENDING,
    )


@transaction.atomic
def create_labor_booking(*, farmer, laborer, booking_date, start_time, duration, location, total_cost):
    conflict_exists = LaborBooking.objects.select_for_update().filter(
        laborer=laborer,
        booking_date=booking_date,
        start_time=start_time,
        status__in=ACTIVE_BOOKING_STATES,
    ).exists()
    if conflict_exists:
        raise ValueError('The selected laborer is already booked for this slot.')

    booking = LaborBooking.objects.create(
        farmer=farmer,
        laborer=laborer,
        booking_date=booking_date,
        start_time=start_time,
        duration=duration,
        location=location,
        total_cost=total_cost,
    )
    order = create_order_record(
        farmer=farmer,
        provider=laborer.user,
        service_type='labor',
        details=f'Labor booking at {location}',
        booking_date=booking_date,
        hours=duration,
        rate=laborer.wage_amount,
        total_amount=total_cost,
    )
    return booking, order


@transaction.atomic
def create_tractor_booking(*, farmer, tractor_owner, booking_date, start_time, duration_hours, location, total_cost):
    conflict_exists = TractorBooking.objects.select_for_update().filter(
        tractor_owner=tractor_owner,
        booking_date=booking_date,
        start_time=start_time,
        status__in=ACTIVE_BOOKING_STATES,
    ).exists()
    if conflict_exists:
        raise ValueError('The selected tractor is already booked for this slot.')

    booking = TractorBooking.objects.create(
        farmer=farmer,
        tractor_owner=tractor_owner,
        booking_date=booking_date,
        start_time=start_time,
        duration_hours=duration_hours,
        location=location,
        total_cost=total_cost,
    )
    order = create_order_record(
        farmer=farmer,
        provider=tractor_owner.user,
        service_type='tractor',
        details=f'Tractor booking at {location}',
        booking_date=booking_date,
        hours=duration_hours,
        rate=tractor_owner.wage_amount,
        total_amount=total_cost,
    )
    return booking, order


@transaction.atomic
def update_order_status(*, booking, provider, service_type, status):
    try:
        Order.objects.select_for_update().filter(
            user=booking.farmer,
            provider=provider,
            service_type=service_type,
            status__in=ACTIVE_BOOKING_STATES + [BookingStatus.CANCELLED],
        ).update(status=status)
    except Exception as exc:
        logger.exception('order_status_update_failed booking_id=%s status=%s', getattr(booking, 'id', None), status)
        raise ValueError('Unable to update order status.') from exc
    Order.objects.select_for_update().filter(
        user=booking.farmer,
        provider=provider,
        service_type=service_type,
        status__in=ACTIVE_BOOKING_STATES + [BookingStatus.CANCELLED],
    ).update(status=status)
