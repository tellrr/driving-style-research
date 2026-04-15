# Research Topic Configuration: Driving Style Research

## Project Goal

We are building a comprehensive knowledge base to inform the design of fleet telematics
services, reports, and alerts centered on driving style analysis. Our data sources are
real-time GPS tracking (coordinates, speed, heading, G-sensor data), optional CAN bus
signals (braking force, gas pedal position, RPM), and optional online tachograph feeds.

The core research goal is to determine which services, reports, and alerts would deliver
the most value to fleet operators — from standard industry offerings to rarely-provided
but high-impact analytics. We want to understand: what constitutes measurably aggressive
or safe driving from telemetry alone; how driving behavior correlates with maintenance
costs, cargo damage, and tire wear; whether driver nationality and regional road surface
quality meaningfully influence telemetry patterns; and how G-force thresholds vary by
vehicle type and category (passenger car, SUV, LCV, truck).

The ultimate deliverable is a prioritized service and report design blueprint: what to
build first, what thresholds and scoring models to use, and what visualizations best
communicate driving quality to fleet managers and drivers.

---

## Research Domain

Fleet telematics, driving behavior analysis, and vehicle dynamics research applied to
commercial fleet management. The domain spans real-world GPS/G-sensor/CAN-bus data
interpretation, industry standards for driver scoring, safety engineering, cargo
logistics, tire science, and cross-cultural driver behavior studies.

**Relevant topics include:** driving style analysis, driver scoring, telematics fleet management, G-force vehicle dynamics, harsh braking detection, harsh cornering, harsh acceleration, eco-driving, fuel efficiency fleet, maintenance prediction telematics, brake wear driving behavior, cargo damage G-sensor, tachograph data analysis, CAN bus fleet, tire wear driving style, road surface condition, driver behavior nationality, cornering speed vehicle category, fleet safety reports, driver performance KPI, fatigue detection telematics, GPS speed profiling, fleet dashboard design, vehicle dynamics passenger car SUV LCV truck

**Irrelevant:** autonomous vehicle control without human driver behavior, pure racing/motorsport without fleet applicability, medical EEG/brain-computer studies without driving context, general traffic engineering without individual driver data, unrelated vehicle engineering (chassis design, engine manufacturing)

---

## Pillars

- Behavior Metrics & Scoring: define measurable driving style events (harsh braking, cornering, acceleration) and driver scoring models from GPS/G-sensor/CAN data
- Safety & Force Thresholds: critical G-force values by vehicle type and category, cornering limits, cargo-safe acceleration profiles, rollover risk
- Cost & Maintenance Impact: correlation between driving events and brake/tire/engine wear, maintenance frequency prediction, fuel consumption impact
- Driver & Route Context: cultural/national driving patterns, road surface quality differences by country, environmental factors influencing telemetry readings
- Service & Report Design: industry-standard fleet telematics reports, rarely-offered analytics, alert threshold recommendations, visualization formats and mockups

---

## Research Subtopics

### 1. Driving Style Classification & Scoring Models
**Why:** The foundation of the whole project. We need to understand how the industry defines
and quantifies "aggressive" vs "smooth" vs "eco" driving from raw telemetry signals. Scoring
models determine what goes into a driver KPI and how reports are structured.

**Keywords:**
- driving style classification, driver behavior scoring, aggressive driving detection
- driving score algorithm, driver KPI fleet, driver performance index
- harsh event detection GPS, harsh braking threshold, harsh acceleration threshold
- driving style telematics, driver risk score insurance telematics
- naturalistic driving study, driver behavior profiling
- eco-driving score, smooth driving index, driver scorecard fleet

**Trusted sources:**
- Transportation Research Part F: Traffic Psychology and Behaviour
- Accident Analysis & Prevention
- IEEE Transactions on Intelligent Transportation Systems
- Journal of Safety Research

---

### 2. G-Force Analysis & Critical Thresholds
**Why:** G-sensor data is our primary signal for detecting dangerous maneuvers. We need to
know what lateral, longitudinal, and vertical G-force values are considered critical, severe,
or normal across different vehicle types and use cases.

**Keywords:**
- lateral G-force cornering threshold, longitudinal acceleration braking G
- G-force vehicle dynamics, accelerometer threshold harsh event
- critical G-force cargo damage, safe G-force passenger vehicle
- vehicle rollover G-force, tipping threshold truck
- vertical G-force road bump, road roughness accelerometer
- IMU data driving analysis, inertial measurement driving behavior
- G-force severity classification, impact detection telematics

---

### 3. GPS Speed Profiling & Heading Analysis
**Why:** Speed and heading change rates are the most widely available signals. Understanding
how speed profiles, speeding events, and rapid heading changes correlate with safety outcomes
is fundamental to building alerts and reports from GPS-only data.

**Keywords:**
- GPS speed profiling fleet, speeding detection algorithm
- heading change rate cornering, GPS-based harsh event detection
- speed limit compliance fleet, speed variance driving style
- GPS telematics data quality, GPS accuracy vehicle tracking
- route speed profile, speed zone compliance
- trajectory analysis driving, GPS driving behavior

---

### 4. CAN Bus Data Interpretation for Driver Behavior
**Why:** CAN bus provides direct access to brake pedal pressure, throttle position, RPM,
and gear selection — far richer signals than GPS alone. Understanding what CAN variables
are most predictive of driving style is critical for customers who have this data.

**Keywords:**
- CAN bus fleet telematics, OBD2 driving behavior, vehicle bus data analysis
- brake pedal pressure driving style, throttle position analysis
- engine RPM driving behavior, gear shift pattern eco-driving
- CAN bus harsh braking, accelerator pedal position fleet
- OBD-II parameter driving score, diagnostic port fleet management
- CAN bus data mining fleet, vehicle data bus driving analysis

---

### 5. Tachograph Data Analysis
**Why:** Digital tachographs are mandatory in commercial transport in Europe and provide
rich driver activity data (driving time, rest time, speed, distance). Integrating tachograph
streams with GPS/G-sensor data opens new analytics dimensions around fatigue and compliance.

**Keywords:**
- digital tachograph data analysis, tachograph fleet management
- tachograph driving time compliance, HOS hours of service telematics
- tachograph speed data quality, DTCO data fleet
- EU tachograph regulation, tachograph smart analytics
- rest period driving safety, fatigue tachograph correlation
- remote tachograph download fleet, tachograph API integration

---

### 6. Braking Behavior & Brake Wear Correlation
**Why:** Harsh braking is one of the most directly measurable and impactful driving behaviors.
Correlating braking event frequency/severity with actual brake component wear rates is the
core of the maintenance-cost analysis pillar.

**Keywords:**
- harsh braking vehicle wear, brake pad wear driving style
- braking aggressiveness maintenance cost, brake wear prediction telematics
- regenerative braking EV fleet, brake deceleration rate
- brake dust emission driving style, brake caliper wear fleet
- predictive maintenance braking, brake wear model telematics
- driver braking pattern fleet, braking distance analysis

---

### 7. Cornering Dynamics by Vehicle Category
**Why:** We specifically need to know whether sedans lose traction later than SUVs at high
cornering speeds, and whether LCV and truck brands differ significantly in max safe cornering
speed. This requires vehicle dynamics research by category.

**Keywords:**
- cornering dynamics sedan vs SUV, lateral stability passenger car category
- SUV rollover risk cornering, sedan lateral G-force limit
- vehicle traction limit cornering speed, understeer oversteer threshold
- light commercial vehicle cornering, van cornering stability
- truck cornering speed limit, articulated vehicle lateral dynamics
- vehicle center of gravity cornering, track width stability
- electronic stability control SUV sedan, ESC intervention threshold
- vehicle category G-force comparison, car type cornering limit

---

### 8. Cargo Safety & Damage Prevention
**Why:** Fleet operators carrying goods need to know which driving events cause cargo damage.
G-force thresholds for cargo safety differ from those for passenger safety. This subtopic
directly informs a specialized report and alert service offering.

**Keywords:**
- cargo damage G-force threshold, freight damage driving style
- cargo securing regulations, load securing vibration
- fragile goods transport G-force, cold chain cargo damage driving
- cargo damage prevention fleet, last-mile delivery damage
- vertical shock cargo, packaging vibration transport
- EN 12195 load securing, cargo restraint telematics
- shock logger cargo, cold chain vibration monitoring

---

### 9. Tire Dynamics: Brand vs. Wear Level
**Why:** The research question is whether tire brand or wear level is more significant for
vehicle dynamics. This matters for interpreting G-force data (worn tires = lower thresholds
before slip) and for maintenance recommendations to fleet operators.

**Keywords:**
- tire wear driving style correlation, tire degradation telematics
- tire brand performance comparison, tread depth vehicle dynamics
- tire wear rate aggressive driving, tire lifespan fleet management
- worn tire cornering limit, tread depth lateral stability
- tire brand G-force threshold, tire compound cornering performance
- fleet tire management, tire wear prediction model
- tire pressure driving behavior, TPMS fleet analytics

---

### 10. Driver Demographics & Cultural Driving Patterns
**Why:** We need to know whether driving style correlates with the driver's country of origin.
This matters for multinational fleet management and for correctly interpreting driver scores
when comparing drivers from different cultural backgrounds.

**Keywords:**
- driving behavior country of origin, cultural driving style differences
- national driving habits telematics, cross-cultural driver behavior
- multinational fleet driver comparison, driver nationality risk profile
- Eastern European driver behavior, Mediterranean driving style
- driving culture differences, traffic psychology national comparison
- insurance telematics driver nationality, cross-border fleet management
- driving norm cultural variation, road user behavior country comparison

---

### 11. Road Surface Quality by Country & Its Impact on Telemetry
**Why:** Road asphalt quality differs by country and may influence both driving style and raw
telemetry signals. Poor roads create "false positive" harsh events in G-sensor data —
distinguishing road-induced vs. driver-induced vibration is a key analytics challenge.

**Keywords:**
- road surface quality country comparison, road roughness index IRI
- road pavement quality Europe, road condition fleet telematics
- road roughness accelerometer separation, IRI telematics
- false positive harsh event road quality, road-induced vibration filter
- road surface driver behavior, pavement condition driving style
- international roughness index fleet, road quality GPS correlation
- Eastern Europe road quality, Nordic road condition

---

### 12. Driver Fatigue Detection via Telematics
**Why:** Fatigue is a major safety risk. Telematics can detect fatigue signatures (heading
variability, speed micro-oscillations, reaction time proxies). This informs a high-value
proactive alert service combining tachograph rest data with sensor patterns.

**Keywords:**
- driver fatigue detection telematics, drowsiness GPS signal
- fatigue driving behavior telematics, micro-sleep detection fleet
- speed variability fatigue, steering entropy fatigue
- heading variability fatigue indicator, lane keeping proxy GPS
- fatigue alert fleet management, hours of service fatigue
- sleep deprivation driving performance, night driving fatigue telematics
- fatigue scoring model fleet, drowsy driving detection algorithm

---

### 13. Fuel Efficiency & Eco-Driving Programs
**Why:** Eco-driving is a mainstream fleet service with proven ROI. Understanding proven
methodology and what KPIs drive fuel savings helps position the eco-driving report and
coaching service as a high-value, low-friction upsell.

**Keywords:**
- eco-driving fuel savings, eco-driving program fleet
- fuel efficiency driving behavior, fuel consumption driving style
- eco-driving score methodology, green driving KPI
- idling fuel waste fleet, engine idle reduction telematics
- coasting behavior eco-driving, anticipatory driving fuel
- eco-driving coaching effectiveness, fuel saving driver feedback
- CO2 emission fleet telematics, carbon footprint fleet driving

---

### 14. Industry-Standard Fleet Telematics Reports & Services
**Why:** Before designing new reports, we must catalog what already exists in the market.
Understanding current state-of-the-art in fleet telematics reporting prevents reinventing
the wheel and reveals the white spaces where novel services can create competitive advantage.

**Keywords:**
- fleet telematics report industry standard, driver scorecard commercial fleet
- fleet management KPI dashboard, telematics platform report
- Samsara driving report, Geotab driver behavior report, Verizon Connect fleet
- MiX Telematics driver safety, Webfleet fleet analytics
- fleet driver coaching report, driver improvement program telematics
- fleet safety report benchmark, driver risk management telematics
- usage-based insurance UBI telematics report, pay-how-you-drive

---

### 15. Real-Time Alerting Systems & Threshold Design
**Why:** Alerts are a core product offering. Designing thresholds that minimize false
positives while catching genuine risk events requires research on optimal cutoff values
and alert fatigue mitigation strategies.

**Keywords:**
- real-time fleet alert system, speeding alert threshold design
- harsh event alert fleet, alert fatigue telematics
- driver alert notification, in-cab coaching alert
- alert threshold optimization, false positive rate telematics alert
- geofence alert fleet, speed zone alert commercial
- driver violation alert, fleet safety alert system design
- push notification driver behavior, real-time coaching feedback

---

### 16. Fleet Report Visualization & Dashboard Design
**Why:** The project explicitly requires AI-suggested report formats and graph mockups for
the daily dashboard output. Research on effective fleet dashboard design and data
visualization for non-technical fleet managers directly feeds the mockup generation task.

**Keywords:**
- fleet dashboard design, telematics visualization best practice
- driver scorecard UI, fleet KPI chart design
- data visualization transportation, fleet management UX
- driver performance dashboard, fleet report template
- heat map driving behavior, speed profile chart fleet
- G-force event visualization, harsh event map fleet
- fleet report PDF template, driver coaching report design
- trip analysis visualization, fleet analytics dashboard UX

---

## Source Priority

| Priority | Source Type | Notes |
|---|---|---|
| 1 | OpenAlex API | Free, no key, 200M+ papers, start here |
| 2 | arXiv API | CS/ML/transportation preprints, very current |
| 3 | PubMed/Entrez | Medical (fatigue, ergonomics) and safety research |
| 4 | Web scraping | Industry blogs, conference proceedings, telematics vendor white papers |
| 5 | GitHub repos | Open source telematics, driving behavior datasets, scoring models |
| 6 | DuckDuckGo search | General web results per keyword, vendor documentation |
