# import asyncio

# from forecast_solar import ForecastSolar, ForecastSolarRatelimit
# from datetime import datetime, timezone, timedelta
# import dataclasses
# from pprint import pprint


# async def main():
#     """Show example on how to use the library."""
#     async with ForecastSolar(
#         # api_key="YOUR_API_KEY",
#         latitude=-33.47308157,
#         longitude=151.3435789,
#         declination=5,
#         azimuth=-90,
#         kwp=16,
#         damping=0,
#         damping_morning=0.5,
#         damping_evening=0.5,
#         horizon="0,0,0,10,10,20,20,30,30",
#     ) as forecast:
#         try:
#             estimate = await forecast.estimate()
#         except ForecastSolarRatelimit as err:
#             print("Ratelimit reached")
#             print(f"Rate limit resets at {err.reset_at}")
#             reset_period = err.reset_at - datetime.now(timezone.utc)
#             # Strip microseconds as they are not informative
#             reset_period -= timedelta(microseconds=reset_period.microseconds)
#             print(f"That's in {reset_period}")
#             return

#         pprint(dataclasses.asdict(estimate))


# if __name__ == "__main__":
#     asyncio.run(main())

import time

local_time_hour = 7
local_time_minutes = time.localtime()[4]
local_time_minutes_tally = (local_time_hour * 60) + local_time_minutes

tariff_start_minutes = 14 * 60
minutes_till_tariff_start = tariff_start_minutes - local_time_minutes_tally

print (minutes_till_tariff_start)
print ()

SOC = 24
target_soc = 15 # Target Soc at end of tariff change (i.e 8pm)

max_soc_decrease_per_min = 0.24 # reduction in soc in 1 min of max discharge (nominal)
max_soc_increase_per_min = 0.18 # increase in soc in 1 min of max charge (nominal)

minutes_till_full = round((100-SOC) / max_soc_increase_per_min)
minutes_till_target = round((SOC - target_soc) / max_soc_decrease_per_min)

print(minutes_till_full)
print(minutes_till_target)

if minutes_till_tariff_start < minutes_till_full:
    print (True)