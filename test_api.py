"""Quick test script for the Switch2 API client."""

import asyncio
import sys

from switch2 import Switch2ApiClient


async def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <email> <password>")
        sys.exit(1)

    client = Switch2ApiClient(sys.argv[1], sys.argv[2])
    try:
        print("Authenticating...")
        customer = await client.authenticate()
        print(f"Customer: {customer}")

        print("\nFetching data...")
        data = await client.fetch_data()
        print(f"Customer: {data.customer}")
        print(f"Registers: {data.registers}")
        print(f"Number of readings: {len(data.readings)}")
        if data.readings:
            print(f"Latest reading: {data.readings[0]}")
            print(f"Oldest reading: {data.readings[-1]}")
        print(f"\nNumber of bills: {len(data.bills)}")
        if data.bills:
            print(f"Latest bill: {data.bills[0]}")
            print(f"Oldest bill: {data.bills[-1]}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
