"""Vaste instellingen. Tijdens het paper trading NIET aanpassen."""

COINS = ["BTC-EUR", "ETH-EUR", "SOL-EUR", "ADA-EUR"]

# Strategie C + marge (getest in backtest, 3 periodes)
SMA_DAYS = 200        # trendgemiddelde
BUFFER = 0.03         # kopen > gemiddelde +3%, verkopen < gemiddelde -3%
RANGE_DAYS = 40       # Wyckoff trading range (L)
RANGE_MAX_ATR = 8     # max. breedte range in ATR (K)
FEE = 0.0025          # 0,25% per transactie (Bitvavo taker)
BUDGET = 20.0         # fictief budget per munt in EUR

# Waarschuwingen
WARN_ZONE = 0.03      # binnen 3% van koop- of verkooplijn

# Verwachting uit de backtest (nov 2023 - nov 2026, 4 munten): 57 transacties in 36 maanden
EXPECTED_TRADES_PER_MONTH = 1.6

DAY_MS = 86_400_000
