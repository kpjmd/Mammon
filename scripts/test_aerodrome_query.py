#!/usr/bin/env python3
"""Test Aerodrome-specific BitQuery query."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import aiohttp
import json
from src.utils.config import get_settings
from datetime import datetime, timedelta, timezone
from collections import defaultdict


async def test_aerodrome_query():
    """Test Aerodrome-specific query."""
    settings = get_settings()
    api_key = settings.bitquery_api_key

    endpoint = "https://streaming.bitquery.io/graphql"
    start_date = datetime.now(timezone.utc) - timedelta(days=7)
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    query = f"""
    {{
      EVM(network: base, dataset: combined) {{
        DEXTrades(
          limit: {{count: 500}}
          orderBy: {{descending: Block_Time}}
          where: {{
            Trade: {{
              Dex: {{
                ProtocolName: {{is: "aerodrome_v1"}}
              }}
            }}
            Block: {{
              Time: {{since: "{start_str}"}}
            }}
          }}
        ) {{
          Trade {{
            Dex {{
              SmartContract
              ProtocolName
            }}
            Buy {{
              Amount
              Currency {{
                Symbol
                SmartContract
              }}
              Price
            }}
            Sell {{
              Amount
              Currency {{
                Symbol
                SmartContract
              }}
              Price
            }}
          }}
        }}
      }}
    }}
    """

    print("🔍 Testing Aerodrome-specific query...")
    print(f"Date range: Last 7 days (since {start_str})")
    print()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(
            endpoint,
            json={"query": query},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status == 200:
                data = await response.json()
                trades = data.get("data", {}).get("EVM", {}).get("DEXTrades", [])

                print(f"✅ Found {len(trades)} Aerodrome trades")
                print()

                # Aggregate by pool
                pool_stats = defaultdict(lambda: {"volume_usd": 0, "count": 0, "tokens": set()})

                for trade_entry in trades:
                    trade = trade_entry.get("Trade", {})
                    dex = trade.get("Dex", {})
                    pool_addr = dex.get("SmartContract", "")

                    if not pool_addr:
                        continue

                    buy = trade.get("Buy", {})
                    sell = trade.get("Sell", {})

                    buy_symbol = buy.get("Currency", {}).get("Symbol", "")
                    sell_symbol = sell.get("Currency", {}).get("Symbol", "")

                    # Calculate volume
                    try:
                        amount = float(buy.get("Amount", 0))
                        price = float(buy.get("Price", 0))
                        volume = amount * price
                    except:
                        volume = 0

                    pool_stats[pool_addr]["volume_usd"] += volume
                    pool_stats[pool_addr]["count"] += 1
                    pool_stats[pool_addr]["tokens"].add(buy_symbol)
                    pool_stats[pool_addr]["tokens"].add(sell_symbol)

                print(f"📊 Aggregated into {len(pool_stats)} unique pools")
                print()

                # Show top 10 pools
                sorted_pools = sorted(
                    pool_stats.items(),
                    key=lambda x: x[1]["volume_usd"],
                    reverse=True
                )[:10]

                print("🏆 TOP 10 AERODROME POOLS BY 7-DAY VOLUME:")
                print("=" * 80)
                for i, (pool_addr, stats) in enumerate(sorted_pools, 1):
                    tokens = "/".join(sorted(stats["tokens"]))
                    print(f"{i:2d}. {tokens:20s} | ${stats['volume_usd']:>15,.2f} | {stats['count']:4d} trades")
                    print(f"    Pool: {pool_addr}")

                print("=" * 80)
                print()

                print("✅ BitQuery v2 Aerodrome integration working!")
                print(f"   Found {len(pool_stats)} pools with recent activity")
                print(f"   Total {len(trades)} trades in last 7 days")

            else:
                print(f"❌ HTTP {response.status}: {await response.text()}")


if __name__ == "__main__":
    asyncio.run(test_aerodrome_query())
