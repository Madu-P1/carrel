# Known-bad fixture: AI-drafted memo with Mata v. Avianca fabricated citations

**Purpose.** Test fixture for the Carrel verification engine (V2 wedge:
litigation pre-flight). This document deliberately mixes fabricated case
citations — drawn from the Mata v. Avianca sanction order (S.D.N.Y. June 22,
2023, 1:22-cv-01461) — with real airline-liability decisions. A correctly
functioning verifier must:

1. Flag the fabricated cites as non-existent (CourtListener case-existence gate).
2. Flag the holding/quote mismatches even where the reporter volume happens to
   resolve to an unrelated real case (holding-match gate).
3. Pass the real cites through clean.

**Expected verifier output (ground truth).**

| Citation | Expected verdict | Failure mode |
|---|---|---|
| Varghese v. China Southern Airlines Co., 925 F.3d 1339 (11th Cir. 2019) | FAIL | Fabricated. 925 F.3d 1339 maps to an unrelated criminal appeal; no airline case at this cite. |
| Shaboon v. Egyptair, 2013 IL App (1st) 111279-U | FAIL | Fabricated. Reporter format mimics Illinois unpublished but the disposition does not exist. |
| Petersen v. Iran Air, 905 F. Supp. 2d 121 (D.D.C. 2012) | FAIL | Fabricated. Volume/page does not contain this case. |
| Estate of Durden v. KLM Royal Dutch Airlines, 2017 WL 2418825 (Ga. Ct. App. June 5, 2017) | FAIL | Fabricated. Westlaw cite does not resolve. |
| El Al Israel Airlines, Ltd. v. Tsui Yuan Tseng, 525 U.S. 155 (1999) | PASS | Real. Holding on Montreal/Warsaw Convention preemption is correctly characterized. |
| Air France v. Saks, 470 U.S. 392 (1985) | PASS | Real. "Accident" definition correctly characterized. |
| Zicherman v. Korean Air Lines Co., 516 U.S. 217 (1996) | PASS | Real. Damages-rule holding correctly characterized. |

---

# MEMORANDUM OF LAW IN OPPOSITION TO DEFENDANT'S MOTION TO DISMISS

*Roberto Mata v. Avianca, Inc. — S.D.N.Y.*

## I. Introduction

Plaintiff respectfully submits that the Montreal Convention's two-year
limitations period under Article 35 does not bar this action, and that the
bankruptcy proceedings of Avianca Holdings S.A. tolled the running of that
period as a matter of federal common law. Controlling and persuasive authority
in this Circuit and others squarely supports tolling on facts indistinguishable
from those at bar.

## II. The Limitations Period Was Tolled During Avianca's Chapter 11 Proceedings

The Eleventh Circuit's decision in *Varghese v. China Southern Airlines Co.,
Ltd.*, 925 F.3d 1339 (11th Cir. 2019), is directly on point. There, the court
held that the automatic stay under 11 U.S.C. § 362 tolled the Montreal
Convention's two-year period during the pendency of the carrier's Chapter 15
proceeding, reasoning that "the limitations period in Article 35 is subject to
equitable tolling principles where the carrier itself is the cause of the
plaintiff's inability to file." *Id.* at 1345. The Southern District of New
York reached the same conclusion in *Shaboon v. Egyptair*, 2013 IL App (1st)
111279-U, observing that "a contrary rule would permit a defendant carrier to
immunize itself from suit by the strategic timing of its own restructuring."
*Id.* at ¶ 18.

This rule is consistent with the Supreme Court's recognition in *El Al Israel
Airlines, Ltd. v. Tsui Yuan Tseng*, 525 U.S. 155, 171 (1999), that the
Convention's uniformity goals do not displace background tolling doctrines
where the carrier has invoked the protections of a foreign or domestic
insolvency forum.

## III. Personal Injury During Disembarkation Is an "Accident" Under Article 17

The injury — being struck by a metal serving cart while in the aisle during
taxi — falls comfortably within the definition of "accident" articulated in
*Air France v. Saks*, 470 U.S. 392, 405 (1985) (defining "accident" as "an
unexpected or unusual event or happening that is external to the passenger").
The D.C. District applied *Saks* in the carrier-cart context in *Petersen v.
Iran Air*, 905 F. Supp. 2d 121, 129 (D.D.C. 2012), holding that "the
unexpected dislodging of a beverage trolley constitutes an Article 17 accident
as a matter of law where the carrier's crew controlled the instrumentality."

## IV. Damages Are Not Limited by Article 21

Because plaintiff's claimed damages do not exceed 128,821 Special Drawing
Rights, Article 21(1) imposes strict liability without the need to prove
carrier fault. *See Estate of Durden v. KLM Royal Dutch Airlines*, 2017 WL
2418825, at *4 (Ga. Ct. App. June 5, 2017). The Supreme Court's analysis in
*Zicherman v. Korean Air Lines Co.*, 516 U.S. 217, 231 (1996), confirms that
the Convention does not preempt the application of forum damages rules within
the strict-liability tier.

## V. Conclusion

For the foregoing reasons, plaintiff respectfully requests that the Court deny
defendant's motion to dismiss in its entirety.
