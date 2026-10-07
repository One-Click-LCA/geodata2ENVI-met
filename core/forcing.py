"""Hourly simple-forcing profiles from a daily minimum and maximum."""


def diurnal_profile(hour_of_min, hour_of_max, value_min, value_max):
    """24 hourly values (index = hour) that change linearly between the extremes.

    The value rises from the minimum to the maximum between their hours and falls
    back over the remaining hours, wrapping around midnight. Works for either
    order of the two hours (temperature usually peaks in the afternoon, relative
    humidity in the early morning).

    :raises ValueError: if both extremes are at the same hour.
    """
    if hour_of_min == hour_of_max:
        raise ValueError('The minimum and the maximum must be at different hours.')
    span = value_max - value_min
    # hours from the minimum to the maximum, going forward in time (with wrap-around)
    rise_hours = (hour_of_max - hour_of_min) % 24
    fall_hours = 24 - rise_hours
    values = []
    for hour in range(24):
        since_min = (hour - hour_of_min) % 24
        if since_min <= rise_hours:
            values.append(value_min + since_min * span / rise_hours)
        else:
            values.append(value_max - (since_min - rise_hours) * span / fall_hours)
    return values
