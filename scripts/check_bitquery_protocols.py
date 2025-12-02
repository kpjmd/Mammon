#!/usr/bin/env python3
"""Check what DEX protocols BitQuery free tier supports on Base."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import aiohttp
import json
from src.utils.config import get_settings
from datetime import datetime, timedelta, timezone
from collections import Counter


async def check_available_protocols():
    """Query BitQuery to see what protocols are available on Base."""
    settings = get_settings()
    api_key = settings.bitquery_api_key

    endpoint = "https://streaming.bitquery.io/graphql"
    start_date = datetime.now(timezone.utc) - timedelta(days=7)
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Query for 100 recent trades to see protocol distribution
    query = f"""
    {{
      EVM(network: base, dataset: combined) {{
        DEXTrades(
          limit: {{count: 100}}
          orderBy: {{descending: Block_Time}}
          where: {{
            Block: {{
              Time: {{since: "{start_str}"}}
            }}
          }}
        ) {{
          Trade {{
            Dex {{
              ProtocolName
              OwnerAddress
            }}
          }}
        }}
      }}
    }}
    """

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print("🔍 Querying 100 recent DEX trades on Base...")
    print()

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(
            endpoint,
            json={"query": query},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status == 200:
                data = await response.json()
                trades = data.get("data", {}).get("EVM", {}).get("DEXTrades", [])

                print(f"✅ Fetched {len(trades)} trades")
                print()

                # Count protocols
                protocols = [
                    t.get("Trade", {}).get("Dex", {}).get("ProtocolName")
                    for t in trades
                ]
                protocol_counts = Counter(protocols)

                print("📊 Protocol Distribution:")
                print("=" * 60)
                for protocol, count in protocol_counts.most_common():
                    pct = (count / len(trades)) * 100
                    print(f"  {protocol:30s} {count:3d} trades ({pct:5.1f}%)")

                print("=" * 60)
                print()

                # Check for Aerodrome
                aerodrome_trades = [
                    t for t in trades
                    if "aerodrome" in t.get("Trade", {}).get("Dex", {}).get("ProtocolName", "").lower()
                ]

                if aerodrome_trades:
                    print(f"✅ Found {len(aerodrome_trades)} Aerodrome trades!")
                    print("Sample:")
                    print(json.dumps(aerodrome_trades[0], indent=2))
                else:
                    print("❌ No Aerodrome trades found in sample of 100")
                    print()
                    print("Conclusion:")
                    print("  • BitQuery free tier likely doesn't include Aerodrome")
                    print("  • May require paid tier ($99/month)")
                    print("  • Alternative: Use factory method with AERODROME_MAX_POOLS=50")

            else:
                print(f"❌ HTTP {response.status}: {await response.text()}")


if __name__ == "__main__":
    asyncio.run(check_available_protocols())
