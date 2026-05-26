# Acquirer Rationale Deep Dive — 2024 US Cybersecurity Precedent Transactions

**DEEP_DIVE_ID:** acquirer_rationale
**Scope:** Cybersecurity acquisitions, United States, 2024-01-01 to 2024-12-31
**Prepared:** 2026-05-26

---

## Manifest Deduplication & Scope Notes

**Duplicates removed:**
- *Venafi / CyberArk* appeared twice in the manifest with identical deal terms. Consolidated into a single entry.
- *Synopsys Software Integrity Group / Clearlake & Francisco Partners* appeared twice (as "Synopsys Software Integrity Group" and "Software Integrity Group (Synopsys business unit)"). Consolidated into a single entry.

**Scope flags:**
- **Darktrace (Thoma Bravo):** Darktrace is headquartered in Cambridge, UK and was listed on the London Stock Exchange. This deal is a UK-domiciled target, not a US cybersecurity acquisition. Included per manifest instruction with flag.
- **HashiCorp (IBM):** HashiCorp is a US-domiciled company (San Francisco) primarily classified as infrastructure automation / DevOps. Its Vault product addresses security lifecycle management (secrets, identity-based security), and the Lincoln International Year-End 2024 Cybersecurity Report includes it as a cybersecurity transaction. Retained with note that its core classification is infrastructure, not pure-play cybersecurity.

**Final deduplicated deal count:** 7 unique transactions.

---

## Deal Status Summary

### Closed Deals (2024)
1. **ZeroFox → Haveli Investments** — Closed May 13, 2024
2. **Venafi → CyberArk** — Closed October 1, 2024
3. **Noname Security → Akamai Technologies** — Closed June 24, 2024
4. **Synopsys Software Integrity Group → Clearlake Capital & Francisco Partners** — Closed H2 2024
5. **HashiCorp → IBM** — Expected close by end of 2024; delayed to Q1 2025 per December 2024 8-K filing
6. **Darktrace → Thoma Bravo** — Completed October 2024 ⚠️ *UK-domiciled target*

### Pending at Year-End 2024
7. **Secureworks → Sophos (Thoma Bravo)** — Announced October 21, 2024; expected close early 2025

---

## Deal 1: ZeroFox Holdings (ZFOX) → Haveli Investments

### Deal Overview
- **Date announced:** February 6, 2024 | **Closed:** May 13, 2024
- **Deal value:** ~$350M enterprise value (all cash; $1.14/share)
- **Deal type:** Take-private (public-to-private via merger agreement)
- **Multiples:** EV/Revenue ~2.0x (based on ~$175M LTM revenue)
- **Premium:** 45% to 90-day VWAP

### Acquirer Profile
**Haveli Investments** is an Austin, TX-based technology-focused private equity firm founded in 2021 by Brian Sheth, co-founder of Vista Equity Partners. Haveli received a $500M anchor investment from Apollo in 2022. The firm invests via control, minority, or structured equity/debt in software, data, gaming, and adjacent sectors. The team draws heavily from Vista Capital Partners and Bain Capital alumni.

**Prior M&A:** Haveli acquired software vendor Certinia (formerly FinancialForce) for nearly $1B in July 2023. The ZeroFox deal was its second major control transaction.

### Strategic Rationale
- **Category thesis:** Haveli identified external cybersecurity (digital risk protection, threat intelligence, EASM) as an "important and expanding category" with long-term secular tailwinds from proliferating digital threats.
- **Platform investment:** ZeroFox was positioned as a leader in Digital Risk Protection and Threat Intelligence with a unified platform spanning external attack surface management, digital risk protection, and breach/takedown response.
- **Operational value creation:** Haveli's approach centers on operational and strategic support to drive innovation, growth, scale, and profitability improvement. The PE firm planned to accelerate go-to-market expansion, invest in new channels, and drive customer acquisition.
- **Public-to-private arbitrage:** ZeroFox had significantly underperformed post-SPAC IPO (2022 IPO at $1.4B valuation vs. $350M EV). The stock was near $1 and facing potential Nasdaq delisting, creating an attractive entry point. The $289M federal contract won in Jan 2024 de-risked the revenue base.

### Synergies & Integration Plan
- ZeroFox retained its brand, CEO (James Foster), and operational independence as a privately held company.
- Integration focused on leveraging Haveli's resources for: (1) platform expansion, (2) new market channels, (3) accelerated innovation, (4) customer acquisition acceleration.
- Monroe Capital provided senior credit facility for the acquisition, indicating leveraged buyout structure.

### Analyst Commentary
- **Wohl & Fruchter LLP** investigated whether the Board acted in shareholders' best interests, citing the $1.14/share price was "well below ZeroFox's 52-week high of $3.49."
- SecurityWeek noted the absence of a go-shop period, which could have drawn higher competing bids.
- The deal was broadly viewed as a valuation reset reflecting broader SPAC-era rerating in cybersecurity.

### Regulatory Considerations
- Standard HSR/antitrust clearance; no material regulatory issues disclosed.
- No known CFIUS concerns (domestic PE acquirer).

---

## Deal 2: Venafi → CyberArk Software (CYBR)

### Deal Overview
- **Date announced:** May 20, 2024 | **Closed:** October 1, 2024
- **Deal value:** ~$1.54B EV (~$1B cash + ~$540M in CyberArk shares)
- **Deal type:** Strategic acquisition (public acquirer / PE-backed seller)
- **Multiples:** EV/ARR ~10.3x (~$150M ARR); 95% recurring revenue
- **Seller:** Thoma Bravo (majority owner since Dec 2020 at $1.15B valuation)

### Acquirer Profile
**CyberArk Software Ltd.** (NASDAQ: CYBR) is the global leader in identity security, headquartered in Newton, MA and Petach Tikva, Israel. Market cap exceeded $10B at announcement. CyberArk is centered on intelligent privilege controls across human and machine identities for business applications, distributed workforces, hybrid cloud, and DevOps environments.

**Prior M&A (selective acquirer):**
- Idaptive (May 2020, $68.6M from Thoma Bravo) — IAM for hybrid/multi-cloud
- Aapi.io (Mar 2022, $17.7M) — identity lifecycle management
- C3M (Jul 2022, $28.3M) — cloud privilege security
- Vaultive (Mar 2018, assets) — cloud security controls
- The Venafi acquisition was CyberArk's largest in its 25-year history.

### Strategic Rationale
- **Machine identity explosion:** CyberArk cited 40–45 machine identities per human identity, driven by cloud migration, IoT proliferation, and GenAI workloads. Machine identities represent the "fastest growing and most complex identity" in enterprises.
- **Unified identity platform:** The deal established an end-to-end platform securing both human and machine identities with intelligent privilege controls. CyberArk's secrets management + Venafi's certificate lifecycle management, PKI, code signing, and SSH security = comprehensive machine identity security.
- **TAM expansion:** CyberArk's TAM grew by ~$10B (from $50B to $60B) through complementary machine identity solutions.
- **Revenue synergies over cost synergies:** CyberArk emphasized top-line growth via cross-sell/upsell through its global sales and channel network. Venafi's business was reportedly growing faster than CyberArk's, positioning the deal to accelerate consolidated top-line growth.
- **Post-quantum readiness:** Shorter certificate lifecycles (398→90 days) and quantum readiness requirements increase demand for automated machine identity management.

### Synergies & Integration Plan
- **Revenue synergies:** Cross-sell and upsell through CyberArk's extensive global enterprise sales and channel partner network. Deep CISO-level relationships in similar large enterprises facilitate realization.
- **Margin accretion:** Expected immediately accretive to non-GAAP margins.
- **Product integration:** Venafi technology was already integrated across multiple CyberArk PAM solutions pre-close. Post-close, CyberArk planned a centralized platform for managing all machine identities (workloads, code, applications, IoT, containers).
- **Deployment flexibility:** Combined solution deployable as SaaS or hybrid to serve organizations of all sizes.

### Analyst Commentary
- **TD Cowen (Shaul Eyal):** Called it CyberArk's largest M&A ever and cited its "strong M&A track record."
- **Enterprise Strategy Group (Todd Thiemann):** "It will enable CyberArk to provide more functionality... Enterprises prefer fewer tools to do more work."
- **AllegisCyber Capital (Bob Ackerman):** Positioned the deal within broader IAM consolidation driven by the "Achilles heel" of identity in cybersecurity.
- **YL Ventures (Nadav Lev):** Predicted the deal would trigger competitive responses from other large vendors seeking comprehensive identity platforms.
- **IDC (Katie Norton):** Highlighted how the deal bridges the gap between historically strong human identity investment and neglected machine identity management.

### Regulatory Considerations
- Standard regulatory approvals; completed without disclosed issues.
- Cross-border element (Israel-domiciled acquirer, US-based target) managed through CyberArk's existing US corporate presence.

---

## Deal 3: Noname Security → Akamai Technologies (AKAM)

### Deal Overview
- **Date announced:** May 7, 2024 | **Closed:** June 24, 2024
- **Deal value:** ~$450M (all outstanding equity)
- **Deal type:** Strategic acquisition (public acquirer / VC-backed target)
- **Multiples:** ~15x EV/ARR (per TechCrunch source citing ~$30M ARR); Akamai disclosed only ~$20M partial-year FY2024 revenue contribution
- **Prior valuation:** Noname was valued at $1B in Dec 2021 ($220M total VC funding)

### Acquirer Profile
**Akamai Technologies, Inc.** (NASDAQ: AKAM) is a cloud computing and cybersecurity company known for its CDN, edge platform, and security solutions. Revenue ~$3.8B (2023). Akamai has been transitioning from a CDN-dominant business toward security and cloud computing, with security representing a growing share of revenue.

**Prior M&A (security-focused):**
- Neosec (2023) — API detection and response (behavioral analytics)
- Guardicore (2021, ~$600M) — microsegmentation
- Linode (2022, ~$900M) — cloud computing
- Numerous smaller security acquisitions over 15+ years

### Strategic Rationale
- **API attack surface explosion:** Akamai's data showed 109% YoY growth in API attacks. APIs are the "connective tissue" of the digital economy and a primary attack vector.
- **Beyond WAAP:** Akamai recognized that its existing Web Application and API Protection (WAAP) platform alone was insufficient for comprehensive API security. WAAP lacks contextual awareness of API business logic and cannot detect abuse attacks, shadow APIs, or zombie APIs.
- **Unified API security platform:** Akamai planned to integrate Noname into a unified "Akamai API Security" product combining: (1) API discovery (shadow/zombie/rogue APIs), (2) posture management, (3) runtime threat detection, (4) shift-left API testing in CI/CD pipelines. Noname customers typically discovered 40% more APIs than anticipated.
- **Deployment flexibility:** Noname offered cloud-hosted, self-hosted, hybrid, and distributed deployment options with broad integrations (AWS, Azure, GCP, F5, Apigee, MuleSoft, Nginx), filling gaps in Akamai's edge-centric architecture.
- **Go-to-market acceleration:** Noname brought additional sales/marketing resources and established channel/alliance relationships. Akamai had seen 200% customer demand growth for API security.

### Synergies & Integration Plan
- Akamai designated the Noname platform as the go-forward product platform for API Security.
- A native connector was launched within weeks to pipe all Akamai customer traffic into the Noname platform for discovery and visibility.
- Best capabilities from the prior Neosec acquisition were selectively incorporated. Akamai acknowledged "some level of product overlap" between Neosec and Noname.
- ~200 Noname employees, including CEO Oz Golan, joined Akamai's Security Technology Group.

### Analyst Commentary
- TechCrunch noted the $450M price was less than half Noname's $1B last valuation, reflecting a broader cybersecurity startup rerating.
- The deal was compared to Wiz's attempted $168M acquisition of Lacework (valued at $8.3B), illustrating how dramatically startup valuations had compressed.
- Akamai CEO Tom Leighton previously stated "Pretty much every enterprise CISO or CIO we talk to today, they acknowledge they don't even know all the APIs they've got."

### Regulatory Considerations
- Standard regulatory approvals; closed within ~7 weeks of announcement.
- No CFIUS or antitrust complications disclosed (Israeli-founded startup with US HQ acquired by US public company).

---

## Deal 4: Synopsys Software Integrity Group → Clearlake Capital & Francisco Partners

### Deal Overview
- **Date announced:** May 6, 2024 | **Expected close:** H2 2024
- **Deal value:** Up to $2.1B (including ~$475M performance-based earnout)
- **Structure:** $1.5B at close + $125M in installments over 5 quarters + up to $475M upon sponsors achieving specified IRR
- **Deal type:** Corporate carve-out / divestiture to PE consortium
- **Multiples:** EV/Revenue ~2.7x–3.5x (based on ~$576–600M estimated SIG revenue; range reflects base vs. max consideration)

### Acquirer Profile
**Clearlake Capital Group, L.P.** — Santa Monica, CA-based PE firm with $75B+ AUM. Sector focus on technology, industrials, and consumer. Known for O.P.S.® (operational improvement) framework. Prior tech acquisitions include Alteryx ($4.4B, Dec 2023 with Insight Partners).

**Francisco Partners** — Leading global PE firm specializing in technology, with ~$45B raised. Known for corporate carve-outs; has invested in 400+ tech companies over 25 years. Prior deals include New Relic ($6.5B, Jul 2023 with TPG).

### Strategic Rationale
**Seller's rationale (Synopsys):**
- Synopsys divested SIG to sharpen focus on its core silicon-to-systems EDA and semiconductor IP businesses amid the AI-driven era, and to facilitate its pending $35B acquisition of Ansys.
- SIG, while a leader in application security testing, was non-core to Synopsys's semiconductor focus.

**Buyers' rationale (Clearlake & Francisco Partners):**
- **Standalone value creation:** SIG was an established leader in application security testing (SAST, DAST, SCA, fuzzing) with a comprehensive product portfolio. As a division of a semiconductor-focused parent, it lacked dedicated investment and go-to-market focus.
- **DevSecOps tailwind:** Security increasingly embedded in DevOps workflows. Generative AI accelerating code generation velocity, introducing new forms of software risk and increasing demand for security testing.
- **Carve-out playbook:** Both firms specialize in carving out divisions and building standalone enterprises. Francisco Partners' consulting operating team brings resources for accelerating growth. Clearlake's O.P.S.® framework targets operational enhancements.
- **Products:** Portfolio includes Coverity (SAST), Black Duck (SCA), Seeker (IAST), Defensics (fuzzing), and a newly launched DAST solution built on Whitehat Security technology.

### Synergies & Integration Plan
- SIG to emerge as a newly independent, privately held application security testing software provider under a new brand name (TBD at announcement).
- Existing management team expected to lead the standalone company.
- Acquirers planned operational enhancements, product portfolio expansion, and growth acceleration as a standalone entity freed from Synopsys's semiconductor-centric priorities.

### Analyst Commentary
- Bloomberg had initially reported potential valuations of $3B+, making the $2.1B (max, including earnout) a discount to expectations.
- QA Financial noted a pending lawsuit from Sunstone Partners, which alleged Synopsys violated an exclusivity agreement for the testing elements within SIG prior to the broader sale.
- The deal was seen as part of broader divestiture activity by semiconductor companies exiting non-core software businesses.

### Regulatory Considerations
- Standard regulatory approvals required.
- The Sunstone Partners lawsuit (Delaware Chancery Court, Case 2024-0261) was ongoing at announcement but did not appear to block the transaction.

---

## Deal 5: Secureworks (SCWX) → Sophos (backed by Thoma Bravo)

### Deal Overview
- **Date announced:** October 21, 2024 | **Expected close:** Early 2025
- **Deal value:** ~$859M (all cash; $8.50/share)
- **Deal type:** Public-to-private (PE-backed acquirer purchasing public company majority-owned by Dell)
- **Multiples:** EV/Revenue ~2.3x (FY2024 $365.9M); EV/LTM Revenue ~2.5x (~$346.5M); EV/ARR ~3.0x (~$290M Total ARR); Premium to 90-day VWAP: 28%
- **Seller:** Dell Technologies (~80% voting power)

### Acquirer Profile
**Sophos** is an Oxford, UK-headquartered cybersecurity provider with 600,000+ organizations and 100M+ users. Acquired by Thoma Bravo for $3.9B in March 2020. Sophos offers endpoint, network, email, and cloud security products managed through Sophos Central, powered by its Sophos X-Ops threat intelligence unit. Sophos launched vendor-agnostic MDR services in late 2022 and has seen rapid adoption.

**Thoma Bravo** — One of the world's largest software-focused PE firms with $160B+ AUM. Cybersecurity portfolio valued at ~$45B includes McAfee, Proofpoint, SailPoint, Ping Identity (merged with ForgeRock), Sophos, Darktrace, and others. Has acquired/invested in 490+ companies.

**Prior M&A (Sophos, selected):**
- 18 acquisitions since 1985 founding; largest prior: Invincea (~$120M, 2017)
- The Secureworks deal was Sophos's largest acquisition in its 39-year history

### Strategic Rationale
- **MDR/XDR platform consolidation:** Sophos sought to integrate Secureworks' Taegis XDR platform with its own Sophos Central SOC to create a comprehensive detection and response offering. Taegis brings cloud-native data lake architecture, analytics engine, and 20+ years of real-world detection data.
- **Capability expansion:** Secureworks brought differentiated capabilities in: identity detection and response (ITDR), next-gen SIEM, operational technology (OT) security, network detection and response (NDR), and vulnerability detection and response (VDR).
- **Upmarket expansion:** Sophos primarily served SMB/midmarket; Secureworks' 4,000 enterprise customers broadened the target market to large enterprises.
- **Talent acquisition:** Secureworks was recognized for having "many of the best and brightest security professionals in the industry" (ESG analyst Dave Gruber).
- **Managed services shift:** Both companies were transitioning toward managed security services, which IDC forecast would grow to $44B in 2024 and $49.2B in 2025, driven by budget pressures and security talent shortages.
- **Channel synergies:** Both organizations were partner-centric, creating expanded channel value.

### Synergies & Integration Plan
- Sophos CEO Joe Levy planned to bring "the best hits of the two operations" together — Taegis inside Sophos Central with unified security operations.
- Integration would deliver MDR, VDR, managed risk, and ITDR services through combined capabilities.
- Emphasis on collaborative workflows across MDR business, customers, and MSP/MSSP partners.
- Key challenge identified: enabling collaboration among security operations teams, customers, and the channel ecosystem.

### Analyst Commentary
- **ESG (Dave Gruber):** "A great move for Sophos... Scaling operations to serve an audience of this size is challenging, making this acquisition a smart move."
- **Omdia (Eric Parizo):** Characterized the deal as a "bit of a pivot" for Sophos, reflecting an industry shift toward service-solution hybrid offerings. Called Secureworks' exit "a reasonable decision to recoup value for shareholders" given declining revenue and headcount.
- **IDC (Craig Robinson):** Praised Taegis for "great detection and response capabilities" but noted Sophos has a more vendor-independent MDR model.
- **Forrester:** Did not include Secureworks in its 2024 11-vendor XDR evaluation (Sophos was ranked 8th).
- **CRN/industry:** The deal was seen as part of Dell's ongoing divestiture of non-core security assets (preceded by the $2.08B sale of RSA to STG in 2020).

### Regulatory Considerations
- Subject to customary closing conditions and regulatory approvals.
- Dell special committee involvement given ~80% voting power; reviewed under applicable fiduciary standards.
- Goldman Sachs, Barclays, BofA, HSBC, and UBS provided financial advisory and debt financing for Sophos.

---

## Deal 6: HashiCorp, Inc. (HCP) → IBM

### Deal Overview
- **Date announced:** April 24, 2024 | **Expected close:** End of 2024 (delayed to Q1 2025)
- **Deal value:** $6.4B EV ($35/share, all cash)
- **Deal type:** Strategic acquisition (public-to-subsidiary)
- **Multiples:** EV/Revenue ~10.9x (FY2024 revenue ~$583M per Lincoln International)
- **Premium:** ~43% over closing share price on April 22, 2024

### Acquirer Profile
**IBM Corporation** (NYSE: IBM) is a leading provider of hybrid cloud and AI solutions operating in 175+ countries. Revenue ~$62B. IBM's strategy is centered on hybrid cloud (anchored by Red Hat OpenShift) and AI (watsonx platform). IBM has been actively acquiring infrastructure and security companies to build an end-to-end hybrid cloud platform.

**Prior M&A (recent, selected):**
- Red Hat (2019, $34B) — hybrid cloud/Linux
- Apptio (2023, $4.6B) — cloud financial management
- Turbonomic (2021, ~$1.5B) — AIOps
- Numerous smaller security acquisitions; note IBM also *divested* its QRadar SaaS portfolio to Palo Alto Networks in 2024

### Strategic Rationale
- **Hybrid cloud platform for AI era:** HashiCorp's Infrastructure Lifecycle Management (Terraform) and Security Lifecycle Management (Vault, Boundary) capabilities complement IBM's existing Red Hat portfolio to create a comprehensive end-to-end hybrid cloud platform. GenAI deployment is driving explosive growth in cloud workloads and infrastructure complexity.
- **Terraform as industry standard:** Terraform is the de facto standard for infrastructure-as-code provisioning across multi-cloud environments. 85% of Fortune 500 use HashiCorp products; 500M+ community downloads in FY2024.
- **Red Hat synergies:** The combination of Red Hat Ansible Automation Platform (configuration management) with Terraform (infrastructure provisioning) simplifies hybrid cloud application deployment. HashiCorp products are cloud-agnostic and complement IBM's commitment to open-source and hyperscaler partnerships.
- **TAM expansion:** Addresses the $1.1T total cloud opportunity (per IDC, 2023) with high-teens CAGR through 2027.
- **Security lifecycle management:** Vault provides identity-based security and secrets management; Boundary provides zero-trust remote access. These directly address security use cases but are part of a broader infrastructure stack.
- **Go-to-market leverage:** IBM's global sales presence across 175 countries significantly expands HashiCorp's reach beyond its 4,400 existing customers.

### Synergies & Integration Plan
- HashiCorp to operate as a division within IBM Software, reporting to SVP Rob Thomas.
- Existing leadership (CEO Dave McJannet, CTO Armon Dadgar) to continue running day-to-day operations.
- HashiCorp Cloud Platform (HCP) planned as a broader platform for delivering additional IBM portfolio services.
- Expected accretive to Adjusted EBITDA within first full year post-close; free cash flow accretive in year two. Margin expansion anticipated through operating efficiencies (partly through consolidating go-to-market into IBM's existing sales infrastructure).

### Analyst Commentary
- **Architecting IT:** Raised questions about how IBM would balance Ansible and Terraform capabilities, and whether the acquisition would strengthen the OpenTofu fork justification.
- **Third Bridge (Jordan Berger):** Characterized the deal as "a strategic step forward in the company's agnostic hybrid cloud strategy."
- The acquisition was broadly seen as IBM's continued bet on hybrid cloud infrastructure management, following the Red Hat acquisition playbook.
- Some analysts questioned whether HashiCorp's loss-making financials (despite revenue growth) warranted the 10.9x revenue multiple.

### Regulatory Considerations
- Subject to HSR antitrust review, shareholder approval, and foreign regulatory clearances.
- Key shareholders holding ~43% of voting power signed a voting agreement to support the deal.
- December 2024 8-K disclosed the expected close was pushed from end-of-2024 to Q1 2025, likely reflecting extended regulatory review timelines.
- **Scope note:** HashiCorp is primarily an infrastructure automation company. Its inclusion in cybersecurity transaction comps reflects Vault's security capabilities but should be weighted accordingly.

---

## Deal 7: Darktrace → Thoma Bravo (Luke Bidco Ltd.)

### ⚠️ Scope Flag
**Darktrace is headquartered in Cambridge, UK and was listed on the London Stock Exchange.** This is not a US-domiciled target. Included per manifest instruction but flagged as outside the stated "United States" research scope.

### Deal Overview
- **Date announced:** April 26, 2024 | **Completed:** October 2024
- **Deal value:** ~$5.3B (fully diluted equity value); EV ~$4.99B (all cash, $7.75/share)
- **Deal type:** Take-private via UK scheme of arrangement
- **Multiples:** EV/Revenue ~8.1x (LTM revenue ~$616M per Lincoln International); EV/Adj. EBITDA ~34x ($146M LTM Adj. EBITDA)
- **Premium:** 20% to last close; 44.3% to 3-month VWAP; 148.1% to IPO price

### Acquirer Profile
**Thoma Bravo, L.P.** — Chicago-based PE firm, one of the world's largest software-focused investors with $160B+ AUM. Has invested in 490+ companies representing ~$265B in enterprise value. Cybersecurity portfolio valued at ~$45B includes McAfee, Proofpoint, SailPoint, Ping Identity/ForgeRock, Sophos, LogRhythm/Exabeam, Intel471, and Illumio.

### Strategic Rationale
- **AI-native cybersecurity thesis:** Thoma Bravo identified Darktrace as a pioneer in self-learning AI for cybersecurity — the ActiveAI Security Platform autonomously detects and responds to known/unknown threats across cloud, apps, email, endpoint, network, and OT environments. Unlike signature-based approaches, Darktrace continuously learns organizational patterns.
- **Market fragmentation:** The cybersecurity market remains "fragmented, with few truly global players." Thoma Bravo's M&A expertise could help consolidate Darktrace's position through bolt-on acquisitions in the highly fragmented market.
- **Operational improvement:** Thoma Bravo planned to apply its 40-year operational playbook (best practices, cost optimization) to build a "best-in-class software franchise." Specifically: reduce non-critical administrative costs while investing in R&D and growth.
- **LSE undervaluation:** Darktrace argued its shares traded "at a significant discount to its global peer group" on the London Stock Exchange. Private ownership would remove the public market discount and allow long-term investment without quarterly earnings pressure.
- **Prior attempt:** Thoma Bravo initially attempted to acquire Darktrace in 2022 but the deal collapsed over pricing disagreements. Darktrace subsequently recovered from short-seller allegations (EY gave clean audit), which improved its negotiating position but the PE firm ultimately prevailed at a higher price.

### Synergies & Integration Plan
- Darktrace to continue operating as a standalone business, headquartered in Cambridge, UK.
- No material restructuring, material headcount reduction, or HQ relocation planned.
- Thoma Bravo committed to a 6-month post-close review to implement operational best practices.
- Cross-portfolio opportunities with other Thoma Bravo cybersecurity assets (Sophos, SailPoint, etc.) were implied but not formally disclosed.

### Analyst Commentary
- **BankInfoSecurity (Novinson):** Highlighted that the deal came 19 months after prior failed attempt, and positioned Thoma Bravo as capitalizing on market turmoil to buy cybersecurity vendors at a discount.
- **TechMarketView (Baxter):** Called the deal "another nail in the coffin for the UK quoted tech sector."
- **Forrester:** Had rated Darktrace 11th of 13 in NAV evaluation; praised simplified deployment but criticized UI for valuing "flash over functionality."
- **Megabuyte (Kennedy):** Described the delisting as a blow to London's tech investment landscape.

### Regulatory Considerations
- Implemented as a UK scheme of arrangement under Part 26 of the Companies Act 2006, requiring shareholder approval (75% threshold) and UK Court sanction.
- Thoma Bravo engaged proactively with UK regulatory authorities and government stakeholders, recognizing "the specific importance of Darktrace's contribution to the technology ecosystem."
- UK National Security and Investment Act (NSI Act) review was relevant given Darktrace's GCHQ/intelligence community origins and critical infrastructure customer base.
- KKR (11.3% stake), Summit Partners, and Darktrace directors committed to backing the deal.

---

## Cross-Deal Observations

### Acquirer Typology
- **PE take-privates (3 deals):** Haveli/ZeroFox, Thoma Bravo/Darktrace, Clearlake+FP/Synopsys SIG
- **Strategic acquirers (3 deals):** CyberArk/Venafi, Akamai/Noname, IBM/HashiCorp
- **PE-backed strategic (1 deal):** Sophos (Thoma Bravo)/Secureworks

### Dominant Strategic Themes
1. **Identity security consolidation** (CyberArk/Venafi): Human + machine identity on unified platform
2. **API security rollup** (Akamai/Noname): WAAP + dedicated API security for full lifecycle protection
3. **MDR/XDR platform build** (Sophos/Secureworks): Endpoint + managed services + XDR
4. **Hybrid cloud infrastructure** (IBM/HashiCorp): Infrastructure automation + security lifecycle management
5. **PE operational playbook** (Haveli, Thoma Bravo, Clearlake/FP): Take-private undervalued assets, apply operational improvement frameworks, accelerate growth

### Valuation Context
All multiples below are standard valuation multiples per the research scope:

- **Highest EV/Revenue:** IBM/HashiCorp at ~10.9x — reflecting infrastructure-as-code market leadership, 85% Fortune 500 penetration, and platform value
- **Highest EV/ARR:** Noname at ~15x (per TechCrunch source) — reflecting strategic premium for API security despite significant down-round from $1B valuation
- **Lowest EV/Revenue:** ZeroFox at ~2.0x — reflecting public market distress, post-SPAC rerating, and near-delisting dynamics
- **EV/EBITDA:** Only Darktrace disclosed at ~34x — a high multiple reflecting AI/cybersecurity growth premium; Darktrace had $146M LTM Adj. EBITDA on $616M revenue
- **Notable premiums:** Darktrace 44.3% (3mo VWAP); ZeroFox 45% (90-day VWAP); Secureworks 28% (90-day VWAP); HashiCorp 43% (last close)

### Thoma Bravo Dominance
Thoma Bravo appeared in three of seven deals: as seller (Venafi to CyberArk), as acquirer via portfolio company (Sophos/Secureworks), and as direct acquirer (Darktrace). This underscores Thoma Bravo's role as the dominant PE force in cybersecurity, both as a consolidator and as a liquidity provider.
