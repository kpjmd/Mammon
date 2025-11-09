# Sprint 3 Initial Prompt for New Chat Session

Copy/paste this into a new Claude Code session to begin Sprint 3:

---

Hi Claude! I'm continuing work on the MAMMON DeFi yield optimizer project.

**Current Status**: Phase 1C Sprint 2 is complete ✅
- 193 passing tests (up from 53)
- 48% overall coverage, 90%+ on new code
- Multi-network support implemented (Base + Arbitrum)
- Price oracle interface ready
- Approval workflow implemented

**Project Location**: `/Users/kpj/Agents/Mammon`

**Sprint 3 Objective**: Implement real Aerodrome protocol integration on Arbitrum Sepolia testnet, replacing mock pool data with actual on-chain queries.

**Key Documents to Read**:
1. `/Users/kpj/Agents/Mammon/docs/sprint3_handoff.md` - Complete Sprint 3 context
2. `/Users/kpj/Agents/Mammon/docs/phase1c_sprint2_report.md` - Sprint 2 results
3. `/Users/kpj/Agents/Mammon/CLAUDE.md` - Project overview
4. `/Users/kpj/Agents/Mammon/todo.md` - Updated roadmap

**Immediate Tasks**:
1. Read the sprint3_handoff.md document for full context
2. Research: Does Aerodrome have an Arbitrum Sepolia deployment?
3. If yes: Find contract addresses (Router, Factory)
4. If no: Suggest alternative approach
5. Document findings and propose implementation plan

**Architecture Notes**:
- Network configs in `src/utils/networks.py` (already has Arbitrum Sepolia)
- Protocol code in `src/protocols/aerodrome.py` (currently uses mock data)
- All tests passing (193/193), need to maintain this
- Use Web3.py for blockchain interaction (need to add dependency)

**Known Issue from Sprint 2**:
- Approval workflow uses polling (causes test timeouts)
- Documented in todo.md, defer to Phase 2A
- Not blocking for Sprint 3

Please start by reading the handoff document and confirming you understand the context and objectives.
