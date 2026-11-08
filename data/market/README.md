# Market data

`hashprice_daily.csv`: daily Bitcoin hashprice and hashpower market, 365 days to 2026-11-07.

Source: CloudMineCrypto. Bitcoin hashprice and hashpower market, daily (methodology v1). https://cloudminecrypto.com/data. Licensed under CC BY 4.0. Accessed 7 November 2026. Unchanged from the download.

The backend uses `hashprice_usd_per_th_day` (expected gross mining revenue per TH/s per day) from the latest row to price lost mining revenue. Empty cells mean the source had no reliable reading and are skipped.

Refresh:

```bash
curl -sf "https://cloudminecrypto.com/api/hashpower-market.csv?days=365" -o data/market/hashprice_daily.csv
```
