# 13: Glossary

| Term | Definition |
|------|------------|
| **Abuse ring** | A group of fraudsters recycling shared identity artifacts (UPI VPAs, phones, devices) across multiple merchants |
| **VPA / UPI ID** | Virtual Payment Address, the `name@bank` identifier used for UPI payments |
| **Device fingerprint** | Identifier derived from a device's characteristics, used to recognize repeat devices |
| **Taint propagation** | Spreading risk score from confirmed-fraud nodes to their graph neighbors, discounted by hop distance |
| **Burn-and-rotate** | Ring pattern: an identity is abandoned shortly after its first fraud outcome and replaced by a linked neighbor |
| **Cross-merchant fan-out** | Number of distinct merchants a single entity (device/phone/VPA) has been observed at |
| **Ring-stratified split** | Train/calibration/test split where all events of one ring fall in exactly one split, preventing entity leakage |
| **FP cost** | The rupee cost of one false positive: review labor + lost fulfillment margin + churn risk |
| **BLOCK_REC** | Block recommendation, the system's strongest output; explicitly a recommendation, never an action |
| **Wilson interval** | 95% confidence interval for a proportion, appropriate at small test-set sizes |
| **Chargeback** | Forced payment reversal initiated by the cardholder's bank; merchant loses amount + penalty |
| **Refund abuse** | Fraudulently obtaining refunds (e.g., false non-delivery claims) |
| **DPDP Act** | India's Digital Personal Data Protection Act, 2023 |
| **Federated signal** | Cross-merchant risk insight shared as aggregate counts/recency without exposing other merchants' customer data |
| **Reason code** | Machine-readable tag explaining which detector fired (e.g. `RNG_DEVICE_FANOUT`) |
| **Calibration split** | The 20% holdout used exclusively to lock decision thresholds before the test set is touched |
