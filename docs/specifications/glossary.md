# Glossary

| Term | Definition |
|------|------------|
| **RWA** | Risk-Weighted Assets — credit exposures multiplied by risk weights to determine capital requirements |
| **CRR** | Capital Requirements Regulation (EU 575/2013 as onshored into UK law) — current Basel 3.0 implementation |
| **Basel 3.1** | BCBS finalisation of Basel III reforms, implemented in UK via PRA PS1/26, effective 1 Jan 2027 |
| **SA** | Standardised Approach — risk weights assigned by exposure class and external rating |
| **F-IRB** | Foundation Internal Ratings-Based — firm provides PD, regulator sets LGD/CCF |
| **A-IRB** | Advanced Internal Ratings-Based — firm provides PD, LGD, EAD, CCF |
| **Slotting** | Specialised lending approach — risk weights by supervisory category (Strong/Good/Satisfactory/Weak/Default) |
| **CRM** | Credit Risk Mitigation — collateral, guarantees, and provisions that reduce capital requirements |
| **EAD** | Exposure at Default — estimated exposure amount at the time of default |
| **PD** | Probability of Default — estimated likelihood of obligor default within one year |
| **LGD** | Loss Given Default — estimated loss as percentage of EAD if default occurs |
| **CCF** | Credit Conversion Factor — converts off-balance sheet amounts to on-balance sheet equivalents |
| **CQS** | Credit Quality Step — standardised rating scale (1=AAA/AA, 2=A, 3=BBB, etc.) |
| **Output Floor** | Basel 3.1 minimum: IRB RWA must be at least X% of SA-equivalent RWA |
| **PRA** | Prudential Regulation Authority — UK banking regulator |
| **BCBS** | Basel Committee on Banking Supervision — global standard setter |
| **SME** | Small and Medium Enterprise — turnover < EUR 50m, eligible for supporting factor |

## Regulatory Definitions (PRA PS1/26)

Long-form regulatory definitions introduced by PRA PS1/26 Appendix 1 (effective 1 January
2027). Quoted verbatim from the PS1/26 Glossary unless marked otherwise.

### Vehicle financing arrangement

**PRA PS1/26 Glossary (Appendix 1, p. 27) — verbatim:**

> "**vehicle financing arrangement** means a loan, lease or other finance arrangement in
> respect of vehicle classes AM, A1, A2, A and B and B1 as specified in Parts 1 and 3 of
> Schedule 2 of The Motor Vehicles (Driving Licenses) Regulations 1999, provided that such
> arrangement does not qualify as an object finance exposure for the purposes of Articles
> 122A and 122B."

**Plain English:** Retail-style financing (loan, lease, or hire-purchase) for a passenger
car, motorcycle, moped, or small van — i.e. a personal-use vehicle covered by an ordinary
UK driving licence — provided the deal is not a corporate-style object-finance transaction
caught by the SA specialised lending articles (Art. 122A) or the IRB specialised lending
article (Art. 122B).

**Where used in PS1/26:**

- [Art. 123(1)(b)(i)(2)](basel31/sa-risk-weights.md#retail-risk-weights-art-123) — listed as
  an example of a "term loan or lease" that may qualify an SME exposure as a **retail
  exposure** under the Basel 3.1 SA exposure-class waterfall.
- [Art. 123A(1)(b)(i)](basel31/sa-risk-weights.md#retail-risk-weights-art-123) — listed as
  an example of a "term loan or lease" that may qualify a natural-person exposure as a
  **regulatory retail exposure** (eligible for the 75% / 45% risk weight rather than the
  100% other-retail weight).

The definition is purely **inclusive** — it confirms that personal-vehicle finance is a
permissible retail product type. It does not by itself trigger any specific risk weight;
the eligibility tests in Art. 123(1) (granularity, GBP 880,000 threshold) and Art. 123A
(regulatory-retail conditions) still apply.

!!! info "Why the carve-out for object finance"
    The closing proviso ("does not qualify as an object finance exposure for the purposes
    of Articles 122A and 122B") prevents wholesale fleet-financing or commercial-vehicle
    leasing from being routed through the retail risk-weight tables when the cash flows are
    economically those of specialised lending. Where a vehicle deal meets the object-finance
    criteria — typically large commercial vehicles (HGVs, buses, aircraft — vehicle classes
    outside AM/A/B) financed primarily from the asset's revenue stream — it is captured by
    SA specialised lending (Art. 122A, slotted weights) or IRB specialised lending
    (Art. 122B, slotting approach) instead.

!!! note "CRR comparison"
    CRR Art. 4(1) does **not** define "vehicle financing arrangement" — the concept is new
    in PS1/26. Under CRR, vehicle financing was implicitly covered by the generic "retail
    exposure" definition in Art. 123 without an explicit asset-class carve-out. The new
    definition aligns the UK retail boundary with BCBS CRE20.65, which lists "auto loans
    and leases" among the qualifying retail product types and excludes specialised vehicle
    lending.
