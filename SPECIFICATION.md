# SPECIFICATION — ManualChat

## 1. Product Purpose & Target User

ManualChat is an intelligent assistant for complex equipment service and repair manuals. It ingests dense, hundreds-of-pages technical manuals once and allows DIY vehicle owners, mechanics, and hobbyists to ask plain-language questions mid-repair. Rather than forcing users to flip through PDF viewers on a garage workbench or phone, ManualChat delivers synthesized, step-by-step procedures, structured technical specifications (torque limits, fluid capacities, part numbers), and verified page citations linked directly to a targeted document viewer showing the exact source page.

---

## 2. Functional Feature List

### 2.1 MVP Features (Demo Scope)
* **Single-Manual Document Ingestion**: Upload a born-digital equipment or vehicle repair manual (PDF). The system processes text, data tables, and page boundaries into an indexed knowledge base with no manual pre-slicing required by the user.
* **Grounded Natural Language Q&A**: Submit free-form repair and maintenance questions. Answers are synthesized exclusively from the manual's content and include inline, verifiable page citations for every factual statement.
* **Structured Specification Extraction**: Query specific technical parameters (e.g., *"What are the cylinder head torque specs and spark plug gap?"*). The system returns extracted specifications organized into clear key/value tabular cards alongside the source context.
* **Step-by-Step Procedure Generation**: Query repair operations (e.g., *"How do I replace the front brake pads?"*). The system returns an actionable, numbered sequence of operational steps, flags required safety warnings/tools, embeds critical torque/fluid specs directly into relevant steps, and cites the source page for each step.
* **Page-Targeted Document Viewer**: Clicking any inline page citation opens a synchronized document viewer focused immediately on the relevant page slice without requiring the client to download or render the full multi-hundred-page PDF.
* **Honest Gap Acknowledgment**: When a queried procedure, part, or specification is omitted or ambiguous in the manual, the system explicitly states that the manual does not contain the information, refusing to guess, extrapolate, or use ungrounded external training data.
* **Multi-Turn Troubleshooting History**: Follow up on earlier questions within the active session (e.g., *"What size socket does that drain bolt need?"* following an oil change inquiry) while preserving context.

### 2.2 Post-MVP Features (Planned Roadmap)
* **Multi-Vehicle Garage Management**: Create and switch between distinct named vehicle profiles (e.g., "2008 Yamaha Rhino", "2023 Civic") from a vehicle dropdown selector.
* **Multi-Manual Scoping & Comparison**: Attach multiple manuals to a single vehicle (e.g., Factory Service Manual + Haynes Aftermarket Guide). Search across all manuals for that vehicle or scope queries to a specific manual.
* **Multi-Manual Conflict Attribution**: When two manuals for the same vehicle specify conflicting instructions or values, the system highlights both values side-by-side with full attribution to their respective manuals and pages.
* **Scanned & Legacy Document OCR**: Ingest scanned physical manuals with high-noise image pages through an automated OCR pipeline.
* **On-Demand Diagram Inspection**: Zoom into technical schematics, exploded assembly diagrams, and wiring charts with interactive, model-assisted diagram callout explanations.
* **Multi-User Accounts & Lightweight Sharing**: Share vehicle workbooks with collaborators via lightweight access tokens or access-gated sessions.
* **Responsive Mobile Garage Mode**: High-contrast, touch-optimized interface layout for mobile devices on garage workbenches.


---

## 3. Core User Flows

### Flow 1: Ingesting a Repair Manual
1. The user selects a born-digital service manual PDF from local storage and uploads it.
2. The application validates the file format, registers the document, and runs document extraction (capturing prose, tables, and physical page offsets).
3. The application displays an ingestion progress indicator.
4. Once indexing completes, the manual appears in the active document pane as "Ready", displaying title, page count, and total extracted sections.
5. The chat input is unlocked for queries against the manual.

### Flow 2: Grounded Q&A and Specification Lookup
1. The user asks: *"What is the engine oil capacity and drain bolt torque?"*
2. The system searches the indexed manual, identifies the maintenance specifications table, and extracts the exact numbers and units.
3. The system responds with:
   - A structured specification card listing item, value, and units (e.g., `Drain Bolt: 30 Nm / 22 ft·lb`, `Total Capacity: 3.00 L / 3.17 US qt`).
   - A concise explanation of conditions (with vs. without filter replacement).
   - Clickable citation badges (e.g., `[Page 9]`, `[Page 24]`).
4. The user clicks `[Page 9]`; the page viewer instantly displays the page containing the Engine Specifications table.

### Flow 3: Generating a Step-by-Step Procedure
1. The user asks: *"How do I change the engine oil and filter?"*
2. The system identifies the multi-page procedure across the maintenance chapter, identifies relevant tool requirements, and extracts associated tightening torques.
3. The system responds with:
   - Required tools, consumables, and warnings (e.g., warm engine, catch pan).
   - An ordered list of steps (1. Warm up engine, 2. Place container under drain bolt `[Page 82]`, 3. Remove drain bolt and drain oil `[Page 82]`, 4. Replace filter cartridge with specified torque: 17 Nm `[Page 83]`, etc.).
   - A summary table of specs relevant to this exact job.
4. The user clicks `[Page 83]`; the viewer pane updates to display pages 80–85 with page 83 active, allowing the user to inspect the filter housing diagram.


---

## 4. Acceptance Criteria (Testable & Eval-Ready)

### Feature 1: Grounded Factual Accuracy
* **AC 1.1**: Given an ingested manual containing a specific torque specification, when queried for that specification, the system must return the exact numeric value and unit as stated in the manual text or table.
* **AC 1.2**: Given an ingested manual containing contradictory values across sections, the system must report both values and cite their respective pages rather than averaging or picking one arbitrarily.
* **AC 1.3**: Given a question regarding a vehicle component not mentioned in the manual, the system must state that the manual contains no information on that topic and must not output fabricated procedures or values.

### Feature 2: Citation Precision
* **AC 2.1**: Given any factual claim or step in a generated response, the system must attach at least one page citation badge.
* **AC 2.2**: When an inline page citation is verified against the source manual, the physical page referenced must contain the explicit text, table, or diagram supporting the claim.
* **AC 2.3**: Every cited page number displayed to the user must correspond to the visible printed page number on the document, matching the physical slice displayed in the viewer.

### Feature 3: Procedure Completeness & Safety
* **AC 3.1**: Given a request for a mechanical procedure that spans multiple manual pages, the generated procedure must list all required operational steps in chronological sequence.
* **AC 3.2**: When a procedure in the manual includes dedicated safety warnings (e.g., hot fluids, battery disconnect, high pressure), the generated procedure must display those warnings before the hazardous operational step.
* **AC 3.3**: All fasteners referenced in a procedure that have explicit tightening torques in the manual must have their torque values embedded directly into the step or listed in an immediate companion table.

### Feature 4: Viewer Integration & Slicing
* **AC 4.1**: When a user clicks a citation badge `[Page N]`, the viewer component must open and render Page N within 1.5 seconds on local execution.
* **AC 4.2**: The viewer must never request or load the entire 500+ page PDF over the client network pipe for a single citation click; it must load only the targeted section or page slice.
* **AC 4.3**: The rendered page slice in the viewer must support text selection and zoom levels up to at least 200% without loss of vector sharpness.


---

## 5. Domain Model (Functional Perspective)

The conceptual hierarchy defines the relationship between physical assets and operational sessions:

```
[User]
  │
  └── owns 1..N
        ▼
   [Vehicle] (e.g. "2008 Yamaha Rhino 700 FI")
        │
        └── possesses 1..N
              ▼
         [Manual] (e.g. "OEM Service Manual", "Wiring Supplement")
              │
              └── contains 1..N
                    ▼
               [Document Section / Page]
                    │
                    └── yields 1..N
                          ▼
                     [Citations & Specifications]
```

### Domain Entities:
* **Vehicle**: The operational subject of all repairs. All queries, retrieved chunks, and active conversation threads exist inside the scope of a single Vehicle.
* **Manual**: A distinct uploaded publication covering a Vehicle. It possesses user-visible metadata (title, publisher, kind: OEM vs. Aftermarket, page count).
* **Section / Segment**: A logical division within a manual (e.g., "Periodic Checks and Adjustments", "Cooling System") spanning a range of physical pages. Used for contextual document slicing.
* **Page**: The fundamental unit of verification and citation. Represents an individual printed sheet in the manual, containing text, tables, and figures.
* **Specification**: A structured data tuple extracted from a manual: `(Subject, Parameter, Value, Unit, Condition, Source Page)`.
* **Procedure**: An ordered list of operational actions required to achieve a mechanical repair outcome, decorated with warnings, tool requirements, and step-level page citations.

---

## 6. Stated Conflict-Resolution & Boundary Rules

1. **Conflict Resolution Rule**: When multiple manuals or multiple sections within a manual provide conflicting specifications or procedures:
   - The system **must never** silently pick one source.
   - The system **must never** synthesize a middle value or guess compatibility.
   - The system **must** present both values explicitly, attributing each to its source manual name and page number (e.g., *"OEM Service Manual (p. 24) specifies 30 Nm, whereas Chapter 8 (p. 210) specifies 26 Nm for rebuilt casings"*).
2. **Missing Information Rule**: If the manual does not contain an answer:
   - The system must reply: *"The manual does not contain information on [topic]."*
   - The system must not supplement with unverified external vehicle knowledge during procedure generation.
3. **Session Scoping Rule**:
   - A repair conversation is strictly bounded to the currently active Vehicle. Queries cannot bleed into or reference manuals belonging to other vehicles.
4. **Citation Boundary Rule**:
   - A response is invalid if it provides a procedural step or technical specification without an accompanying page reference.

---

## 7. Explicit Non-Goals (What Done Excludes)

The following capabilities are deliberately excluded from the project scope:
* **No Fleet or Inventory Management**: No tracking of vehicle mileage, parts inventory, scheduled service alarms, or maintenance logs.
* **No Diagnostic Trouble Code (OBD-II) Hardware Integration**: No physical connection to vehicle ECUs, ELM327 Bluetooth scanners, or live sensor telemetry.
* **No General Web Search Fallback**: The agent will not search Google, YouTube, or automotive forums when a manual lacks information.
* **No Automated Full-Manual OCR in MVP**: Scanned non-digital manuals requiring heavy OCR image pipelines are excluded from the MVP.
* **No Multi-Tenant Enterprise User Management**: No multi-tenant enterprise RBAC, SAML SSO, or billing integrations.
* **No Public Unauthenticated Web Hosting**: No deployment to open public internet URLs without authentication and spending limit gates.

