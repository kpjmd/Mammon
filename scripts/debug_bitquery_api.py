#!/usr/bin/env python3
"""Debug script to test BitQuery v2 API directly."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import aiohttp
import json
from src.utils.config import get_settings
from datetime import datetime, timedelta


async def test_bitquery_v2():
    """Test BitQuery v2 API with simple query."""
    settings = get_settings()
    api_key = settings.bitquery_api_key

    if not api_key:
        print("❌ No API key found in settings")
        return

    print(f"🔑 API Key present: {api_key[:20]}...{api_key[-10:]}")
    print()

    # Simple test query first
    endpoint = "https://streaming.bitquery.io/graphql"

    # Calculate date
    start_date = datetime.utcnow() - timedelta(days=7)
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"📅 Querying trades since: {start_str}")
    print()

    # Aerodrome factory address
    factory = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"

    # Test 1: Query with factory filter
    query_factory = f"""
    {{
      EVM(network: base, dataset: combined) {{
        DEXTrades(
          limit: {{count: 10}}
          orderBy: {{descending: Block_Time}}
          where: {{
            Transaction: {{
              To: {{is: "{factory}"}}
            }}
            Block: {{
              Time: {{since: "{start_str}"}}
            }}
          }}
        ) {{
          Trade {{
            Dex {{
              OwnerAddress
              ProtocolName
              SmartContract
            }}
          }}
        }}
      }}
    }}
    """

    # Test 2: Query without factory filter (any DEX on Base)
    query_any = f"""
    {{
      EVM(network: base, dataset: combined) {{
        DEXTrades(
          limit: {{count: 10}}
          orderBy: {{descending: Block_Time}}
          where: {{
            Block: {{
              Time: {{since: "{start_str}"}}
            }}
          }}
        ) {{
          Trade {{
            Dex {{
              OwnerAddress
              ProtocolName
              SmartContract
            }}
            Buy {{
              Currency {{
                Symbol
              }}
            }}
            Sell {{
              Currency {{
                Symbol
              }}
            }}
          }}
        }}
      }}
    }}
    """

    # Try both queries
    queries = [
        ("Factory Filter", query_factory),
        ("No Filter (Any DEX)", query_any),
    ]

    print("🔍 Testing BitQuery v2 API...")
    print(f"Endpoint: {endpoint}")
    print(f"Factory: {factory}")
    print()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        for query_name, query in queries:
            print("=" * 80)
            print(f"TEST: {query_name}")
            print("=" * 80)
            print()

            try:
                async with session.post(
                    endpoint,
                    json={"query": query},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    print(f"📡 Response Status: {response.status}")

                    response_text = await response.text()
                    print(f"📊 Response Length: {len(response_text)} bytes")
                    print()

                    if response.status == 200:
                        try:
                            data = json.loads(response_text)
                            print("✅ Valid JSON Response")

                            # Analyze response
                            if "errors" in data:
                                print()
                                print("❌ GraphQL Errors:")
                                for error in data["errors"]:
                                    print(f"   - {error.get('message', 'Unknown error')}")

                            if "data" in data:
                                evm = data["data"].get("EVM", {})
                                trades = evm.get("DEXTrades", [])
                                print(f"✅ Found {len(trades)} DEXTrades records")

                                if trades:
                                    print()
                                    print("Sample Trade:")
                                    print(json.dumps(trades[0], indent=2))
                                    print()

                                    # Check for Aerodrome
                                    aerodrome_count = sum(
                                        1 for t in trades
                                        if "aerodrome" in t.get("Trade", {}).get("Dex", {}).get("ProtocolName", "").lower()
                                    )
                                    print(f"Aerodrome trades: {aerodrome_count}/{len(trades)}")
                                else:
                                    print("⚠️  No trades found")

                        except json.JSONDecodeError:
                            print("❌ Invalid JSON Response:")
                            print(response_text[:500])
                    else:
                        print(f"❌ HTTP Error {response.status}:")
                        print(response_text[:500])

            except Exception as e:
                print(f"❌ Request failed: {e}")
                import traceback
                traceback.print_exc()

            print()


if __name__ == "__main__":
    asyncio.run(test_bitquery_v2())
