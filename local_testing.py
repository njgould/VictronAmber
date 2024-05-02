import asyncio

from forecast_solar import ForecastSolar, ForecastSolarRatelimit
from datetime import datetime, timezone, timedelta
import dataclasses
from pprint import pprint


async def main():
    """Show example on how to use the library."""
    async with ForecastSolar(
        # api_key="YOUR_API_KEY",
        latitude=-33.47308157,
        longitude=151.3435789,
        declination=5,
        azimuth=-90,
        kwp=16,
        damping=0,
        damping_morning=0.5,
        damping_evening=0.5,
        horizon="0,0,0,10,10,20,20,30,30",
    ) as forecast:
        try:
            estimate = await forecast.estimate()
        except ForecastSolarRatelimit as err:
            print("Ratelimit reached")
            print(f"Rate limit resets at {err.reset_at}")
            reset_period = err.reset_at - datetime.now(timezone.utc)
            # Strip microseconds as they are not informative
            reset_period -= timedelta(microseconds=reset_period.microseconds)
            print(f"That's in {reset_period}")
            return

        pprint(dataclasses.asdict(estimate))


if __name__ == "__main__":
    asyncio.run(main())