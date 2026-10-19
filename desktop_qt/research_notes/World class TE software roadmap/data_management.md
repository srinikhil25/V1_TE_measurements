# Data Management for Scientific Instrument Software: Thermoelectric Measurements

## File Formats and Storage Architecture

### Takeaway
HDF5 with NeXus application definitions is the dominant mature standard for scientific instrument data, while Zarr and netCDF4 offer complementary strengths for cloud-native and parallel-write workloads; Bluesky and QCoDeS ecosystems favor HDF5/NeXus, making it the recommended primary format for new thermoelectric measurement software.

### Cited Findings
- HDF5 is built on the container format and "NeXus adds domain-specific rules for organizing data within HDF5 files in addition to a dictionary of well-defined domain-specific field names" — [HDF5 and NeXus](https://dawnsci.org/hdf5/)
- "Zarr is a format for the storage of chunked, compressed, N-dimensional arrays inspired by HDF5" with strengths in "parallel writes and cloud object storage, increasingly the default for large N-dimensional array data in cloud-native pipelines" — [HDF5 vs Zarr vs Parquet Compared](https://casrai.org/compare/hdf5-vs-zarr-vs-parquet)
- "HDF5's strength is a mature, self-describing single-file format for single-writer local workflows" while "Zarr specifically targets parallel, cloud-native workloads" — [A Comparison of HDF5, Zarr, and netCDF4](https://arxiv.org/pdf/2207.09503)
- QCoDeS "includes an HDF5 formatter for saving datasets, and the HDF5Format class is capable of storing and recovering QCoDeS datasets" — [qcodes_loop.data.hdf5_format](https://qcodes.github.io/Qcodes_loop/api/data/hdf5_format.html)
- Quantum Design PPMS "stores data in files that have a .dat extension" with "data files formatted for easy import into numerous commercial spreadsheet, graphing, and analysis programs" — [Physical Property Measurement System PPMS MultiVu Application User's Manual](https://web.njit.edu/~tyson/PPMS_Documents/PPMS_Manual/1070-110%20A2%20.pdf%20PQ%20MVu.pdf)
- Bluesky ecosystem includes "document sinks for the bluesky ecosystem include JSONL, ZMQ (msgpack/JSON), Tiled (HTTP), Kafka, and HDF5 (NeXus-flavored frame writer)" — [Exporting data from Bluesky](https://bcda-aps.github.io/bluesky_training/example/_export_bluesky_data.html)

### Inferences
- For a university thermoelectric lab with primarily local single-writer workflows, HDF5 with NeXus is the most appropriate primary format, offering maturity, tool ecosystem compatibility (especially with Python via h5py and scientific software), and standardization across materials science.
- Zarr should be considered a secondary export format or for future cloud-native data sharing (e.g., if integrating with NOMAD or cloud-hosted analytics), but not as the primary on-disk format for desktop measurement software.
- Plain CSV export remains essential for immediate usability with Excel/graphing tools by non-technical lab members, but should be generated from HDF5 rather than used as primary storage.
- JSON/JSONL sidecars alongside HDF5 provide human-readability for metadata but introduce serialization complexity; NeXus attributes within HDF5 are preferable.

### Gaps
- No specific documentation found on NeXus application definitions tailored to thermoelectric transport (Seebeck, resistivity, thermal transport). NXtransport or similar domain-specific schemas may exist in NIAC working groups but were not located. Recommend checking NIAC (NeXus International Advisory Committee) repository and FAIRmat/NOMAD for domain-specific templates.

---

## Metadata Standards and Schemas for Materials Measurements

### Takeaway
NOMAD/FAIRmat provides the most comprehensive, machine-actionable metadata framework for materials science with modular schemas; EMMO/CHAMEO ontology adds semantic interoperability. For a Japanese academic lab, alignment with ARIM-mdx platform metadata requirements is recommended alongside international NOMAD standards.

### Cited Findings
- NOMAD "contains 19M+ FAIR data entries and is growing as a free, community-driven resource for experimental and computational materials data" — [FAIR-DI News](https://www.fairmat-nfdi.eu/lisenews/page/4/10/8)
- "The backbone of NOMAD's compliance to the FAIR principles is its structured data schema: the NOMAD Metainfo" which provides "a hierarchical and modular structure for metadata (Reusability), with unique naming and human-readable descriptions (Findability), along with categorical typing for linking to ontologies (Interoperability)" — [Shared Metadata for Data-Centric Materials Science](https://arxiv.org/pdf/2205.14774)
- "NOMAD taxonomy includes for each term: i) a curated, human-understandable definition, ii) a controlled list of synonyms, iii) the specification of the physical dimensions, and iv) the expected shape (tensorial rank)" — [FAIR-DI Conference 2024](https://events.fairmat-nfdi.eu/event/9/contributions/213/)
- EMMO is "a common root ontology for the development of interconnected materials modelling ontologies, developed under the umbrella of the European Materials Modelling Council (EMMC)" — [The Elementary Multiperspective Material Ontology (EMMO)](https://ontolearner.readthedocs.io/benchmarking/materials_science_and_engineering/emmo.html)
- CHAMEO is "an ontology for materials characterization which represents the evolution of the CHADA template in an ontological form, allowing to generate FAIR documentation of Characterisation Experiments" and is "conceived as a domain ontology for materials characterisation methodologies, based on EMMO's top and middle level portions" — [CHAMEO: An ontology for the harmonisation of materials characterisation methodologies](https://www.researchgate.net/publication/362202310_CHAMEO_An_ontology_for_the_harmonisation_of_materials_characterisation_methodologies)
- Japan's ARIM project provides "interactive computing services, large-volume cloud storage, direct data transfer from experimental equipment, and high-throughput networking from the supercomputers in Japan" with "11 universities and institutes all over Japan...utilized by over 800 researchers from around 140 organizations" — [ARIM-mdx Data System: Towards a Nationwide Data Platform for Materials Science](https://arxiv.org/abs/2409.06734)
- NIMS DICE platform is "the National Institute for Materials Science (NIMS)...developing the DICE materials data platform to fulfill its role as a data core center in the MEXT-led project to develop materials DX platforms across Japan" — [DICE materials data platform](https://www.eurekalert.org/news-releases/978485)

### Inferences
- Minimal metadata to capture with each run: (1) sample ID and geometry (critical for reproducibility; placeholder 1×1×1 is problematic), (2) operator name and timestamp, (3) instrument identifiers (PPMS chamber, heater model, temperature sensor type, calibration dates), (4) software version + git commit hash (enables reproducibility and debugging), (5) measurement settings snapshot (all configured parameters, not just default assumptions).
- NOMAD Metainfo provides a validated vocabulary that can be embedded in HDF5 attributes, reducing custom schema design burden while improving future data FAIRness. eLabFTW/Kadi4Mat integration should push structured metadata into NOMAD-compatible form.
- For a Shizuoka University lab, participation in ARIM-mdx ecosystem (if available) or alignment with its metadata schema would facilitate future data sharing and multi-institution collaboration; NOMAD metadata should be viewed as complementary, not competing.
- Machine-readable metadata in NeXus attributes or NOMAD-compliant JSON sidecars enables automated validation, discoverability, and re-use; human-readability should not be sacrificed for compactness.

### Gaps
- No public documentation on whether NOMAD has electronic-transport or Seebeck-specific application definitions, or how thermal transport measurements should map to NOMAD schemas. Recommend direct contact with FAIRmat community or NOMAD Lab for guidance on schema inheritance and custom extensions.
- ARIM-mdx technical specifications (exact metadata schema, supported formats, upload protocols) are not publicly available in English. Recommend contacting NIMS Data Integration Center or ARIM project office for integration guidelines.
- No evidence of consensus on whether Bluesky-style modular metadata (Run Start / Event Descriptor / Event documents) or NOMAD's hierarchical Metainfo is preferable for long-term archival; likely complementary (Bluesky for live streaming, NOMAD for archive).

---

## Raw vs. Processed Data Retention and Provenance

### Takeaway
Immutable raw data must be stored separately from derived quantities with full provenance chains (Bluesky/RO-Crate model); keep raw instrument readings and configuration snapshots, derive Seebeck and resistivity from them reproducibly, and track computation steps via W3C PROV or RO-Crate for FAIR re-analysis.

### Cited Findings
- Bluesky's event model "separates concerns through linking: Event Descriptors contain configuration metadata, while Events reference their descriptor via a foreign key. All documents link back to a Run Start document, creating a coherent data lineage. Events may contain literal values or pointers to external storage" — [Bluesky's Event Model Structure](https://blueskyproject.io/event-model/main/explanations/data-model.html)
- RO-Crate captures provenance "through three profiles of increasing granularity: Process Run Crate, Workflow Run Crate, and Provenance Run Crate" with "alignment with W3C PROV standards" and enables "programmatic workflow re-execution" and "extraction and validation of provenance information through SPARQL queries" — [Recording provenance of workflow runs with RO-Crate](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0309210)
- "A major research article 'Recording provenance of workflow runs with RO-Crate' was published in PLoS ONE in September 2024...The research describes the model, its alignment to standards such as W3C PROV, and its implementation in six workflow systems" — [PLOS ONE Volume 19, Issue 9](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0309210)
- Quantum Design PPMS "The Reprocess command allows you to recompute thermal transport results from an existing TTO data file by changing the sample's estimated geometry and emissivity, and write these results out to a new data file" — [PPMS TTO User's Manual](https://web.njit.edu/~tyson/PPMS_Documents/PPMS_Manual/1684-100%20Rev.%20B0%20TTO.pdf)

### Inferences
- Store raw T1, T2, ΔT, heater V/I, sample geometry as immutable Event records in HDF5; derived Seebeck (from V vs ΔT slope) and resistivity should be recomputable from raw data, not stored as primary facts.
- Include computation metadata in NeXus/RO-Crate: (1) which raw fields were used, (2) algorithms applied (linear fit method, filtering, outlier removal), (3) parameter values (fit window, threshold), (4) who triggered reprocessing and when.
- Maintain a "run state" enum (running, paused, crashed, completed_with_validation, completed_unvalidated, reprocessed) in database; "running" state after crash is a data integrity problem—must be resolved on startup with user confirmation.
- If sample geometry is left as 1×1×1 placeholder, flag this in metadata with a `is_placeholder` boolean; derive Seebeck from raw V and ΔT directly and store both raw and area-normalized resistivity so re-analysis with corrected geometry is feasible.

### Gaps
- No clear guidance on whether intermediate computation results (e.g., fitted parameters, uncertainty estimates) should be stored alongside raw data or regenerated on each access. Recommend adopting Bluesky convention: store raw + minimal derived, regenerate analysis on demand or cache with provenance record.

---

## Electronic Lab Notebooks and LIMS Integration

### Takeaway
eLabFTW and Kadi4Mat both provide REST APIs for programmatic data ingestion from measurement software; push structured run metadata immediately after completion (or at user request) to ELN for human review, tagging, and long-term archival without tight integration coupling.

### Cited Findings
- eLabFTW "provides a REST API (v2) that allows programmatic access to experiment data" with "core entity management" via "Experiments, Items, Compounds" endpoints and "administrative" endpoints for "Users, Teams, API Keys" — [eLabFTW REST API v2 Documentation](https://doc.elabftw.net/api/elabapi-html/)
- Kadi4Mat "provides high-level interaction with Kadi4Mat's HTTP API in Python as well as a Command Line Interface" via the kadi-apy library (kadi_apy on PyPI) — [kadi-apy documentation](https://kadi-apy.readthedocs.io/)
- "Tribometers controlled with LabView can be integrated with Kadi4Mat using the kadi-apy wrapper library's command line interface to communicate with Kadi4Mat's HTTP API, demonstrating how measurement instruments can be connected to these platforms for research data management" — [Managing FAIR Tribological Data Using Kadi4Mat](https://www.mdpi.com/1465596)
- "Both eLabFTW and Kadi4Mat are part of the ELN Consortium, which supports the ELN file format to improve interoperability between different electronic lab notebook services" — [eLabFTW GitHub Topics](https://github.com/topics/elabftw?o=desc&s=stars)

### Inferences
- ELN integration should be **optional and asynchronous**: after a measurement run completes successfully, offer user a "push to ELN" button that POSTs a summary (run metadata, sample info, key results, HDF5 file reference/link) to eLabFTW or Kadi4Mat without blocking the measurement workflow. Desktop app should not fail if ELN is unreachable.
- Data flow: (1) Measurement software writes HDF5 + SQLite record locally, (2) user reviews in GUI (plots, statistics, data quality flags), (3) optionally clicks "Archive to ELN" → app POSTs to REST API, ELN stores reference to local file path or uploads copy, (4) user tags/annotates in web interface.
- For Shizuoka University: Kadi4Mat may be integrated with ARIM-mdx platform; if so, use kadi-apy for direct integration rather than eLabFTW. Recommend contacting ARIM project office for current ELN recommendation.
- Store ELN record ID/URL in SQLite database after successful push, enabling future two-way sync (e.g., user updates sample ID in ELN, pull that change back into measurement software).

### Gaps
- No specific guidance on whether to push HDF5 files to ELN (data duplication, storage cost) or only metadata + reference (higher ELN brittleness if reference breaks). Recommend hybrid: push metadata and CSV summary to ELN, keep HDF5 as primary in local database, with periodic backup to shared network drive.
- ARIM-mdx ELN recommendations and API specifications are not publicly available. This is a blocking gap for Japan-specific integration and requires direct engagement with project stakeholders.

---

## Audit Trails, Data Integrity, and Crash Recovery

### Takeaway
Implement ALCOA+ compliance through append-only audit logs (one log entry per data point insert/update, never overwrite), SQLite write-ahead logging (WAL) for crash durability, and per-run hash records; detect and mark orphaned "running" state runs on startup.

### Cited Findings
- ALCOA+ is "a nine-principle data integrity framework consisting of: Attributable, Legible, Contemporaneous, Original, Accurate, Complete, Consistent, Enduring, and Available" — [ALCOA & ALCOA+ Principles Explained](https://totallab.com/resources/alcoa-principles/)
- "A comprehensive audit trail exists linking each data point to its origins and transformations, which is a key component of the 'Traceable' principle. For electronic systems, immutable audit logs of every create/modify/delete action (who, what, when) should be enabled" — [Audit Trails and Data Integrity in AI-Assisted Regulated Labs](https://www.labmanager.com/audit-trails-data-integrity-and-ai-what-regulated-labs-need-to-know-35642)
- "When a result is corrected, the system retains the original value and logs the change as a new entry in the audit trail, with the original data point never overwritten" — [Lab Data Integrity: Implementing ALCOA+ in Digital Systems - Sandorian](https://sandorian.com/labs/kb/lab-data-integrity-alcoa-plus-principles)
- "Record every data creation, modification, and deletion, capturing the who, what, when, and why of each change in tamper-proof, append-only audit logs" — [Data Integrity ALCOA+ in Effluent & Industrial Labs](https://www.zendolims.com/blog/data-integrity-effluent-industrial-laboratories.html)
- SQLite "Write-Ahead Logging (WAL) is a technique used in storage systems to ensure the durability and consistency of transactions" with the protocol: "the log entry for any modification must be written to disk before the modified data is written to disk" and "all log entries for a transaction must be written to disk before the transaction can be committed" — [Write-Ahead Logging](https://en.wikipedia.org/wiki/Write-ahead_logging)
- "In event of system crash/failure, database can use WAL to restore database to a consistent state by replaying the log from last committed transaction forward, reapplying the changes that were not yet permanently written to the data files" — [Write-Ahead Logs Explained: How Databases Survive Crashes](https://grindengineer.substack.com/p/write-ahead-logs-explained-how-databases-survive-crashes)
- "SQLite ships a readable version of WAL mode where it checkpoints automatically once the WAL file crosses 1000 pages, moving those transactions back into the main database file" — [Write-Ahead Logging](https://tool.oschina.net/uploads/apidocs/sqlite/wal.html)

### Inferences
- Enable SQLite WAL mode immediately (PRAGMA journal_mode=WAL). At startup, check for orphaned `-wal` and `-shm` checkpoint files and recover gracefully.
- Add an `audit_log` table with columns: (log_id, run_id, timestamp, user, action, table_name, record_id, old_value, new_value, reason). Insert one row per measurement point (e.g., every 50 points from the current behavior), never UPDATE or DELETE from this table—only INSERT.
- Compute SHA-256 hash of each completed run's raw data block (T1, T2, ΔT, V, I time series) and store in database. On re-opening a run, recompute hash and warn if it differs (data was corrupted or modified externally).
- On application startup, scan `runs` table for `state='running'`. If found: (1) check last modification timestamp, (2) if < 1 hour old, prompt user "Resume? Cancel? Mark failed?", (3) if > 1 hour, warn "This run crashed; data may be incomplete" and set `state='crashed'`.
- Current practice (JSON blob per data row, SHA-256 only for I-V) is insufficient. Recommend: store raw numeric columns (T1, T2, ΔT, V_sample, I_heater, etc.) as separate rows in `data_points` table linked to run_id, with per-run hash and audit trail.

### Gaps
- No clear standard for how to handle partial datasets from crashes. Should a run with 60 of 100 planned points be marked complete/incomplete, and what does that mean for later Seebeck coefficient estimation? Recommend: always compute and report uncertainty, flag runs with <N% of planned data points.

---

## Database Schema Evolution: Alembic and SQLite

### Takeaway
Use Alembic with SQLAlchemy for version-controlled schema migrations; auto-run migrations on application startup with user confirmation and pre-migration backups; SQLite's "batch" mode handles ALTER operations safely.

### Cited Findings
- Alembic is "the de facto standard for database migrations in Python applications using SQLAlchemy" providing "a lightweight migration framework that integrates seamlessly with SQLAlchemy, enabling you to version control your database schema and apply changes safely across environments" — [How to Handle Database Migrations with Alembic](https://oneuptime.com/blog/post/2025-07-02-python-alembic-migrations/view)
- "Recognizing SQLite's limitations with certain ALTER operations, Alembic offers a 'batch' mode that allows for complex schema changes by creating a new table with the desired schema and copying data from the old table" — [Simplify Database Migrations using Python with Alembic](https://medium.com/@romina.elena.mendez.escobar/simplify-database-migrations-using-python-with-alembic-f8aa3df36449)
- "Alembic maintains a single table called alembic_version in your database that tracks the current migration version" and provides "rollback capabilities for safe deployments" — [Mastering Alembic Migrations in Python: A Comprehensive Guide](https://thinhdanggroup.github.io/alembic-python/)
- "The tool can automatically generate migration scripts by comparing the current state of the database schema to the desired state defined in SQLAlchemy models, streamlining the migration process by reducing manual effort and potential errors" — [Beginner's Guide to Alembic and SQLAlchemy in Python](https://medium.com/@evembijo/beginners-guide-to-alembic-and-sqlalchemy-in-python-manage-your-database-like-a-pro-9395b5b5080d)
- For SQLite setup: "If you want to use SQLite (simple local database), no extra installation is needed beyond pip install sqlalchemy alembic. For SQLite, set your database URL to: sqlalchemy.url = sqlite:///myapp.db" — [Python Database Migrations with Alembic — Complete Guide (2026)](https://dev.to/sharma_nitesh_cab3ef0e7dd/python-database-migrations-with-alembic-complete-guide-2026-kbl)

### Inferences
- Replace current `create_all()` pattern with explicit Alembic migrations. Initialize Alembic: `alembic init alembic_env`, then each time schema changes (e.g., adding `audit_log` table, adding `is_placeholder` column to sample geometry), run `alembic revision --autogenerate -m "Add audit_log table"`.
- At application startup: (1) check if `alembic_version` table exists, (2) if not, run `alembic upgrade head` to initialize, (3) if it exists, compare version to current code version—if behind, prompt user "Database schema needs upgrade. Backup will be created before proceeding." Create backup (copy .db file to `.backup_TIMESTAMP.db`), then run `alembic upgrade head`.
- Use Alembic's batch mode for SQLite: in migration scripts, wrap ALTER operations with `with op.batch_alter_table(...)` to avoid "ALTER TABLE not supported" errors.
- Store the Alembic version in `alembic.ini` and version control it; include migration scripts in git so schema evolution is auditable alongside code.
- For existing installations (current SQLite with create_all), provide a one-time migration guide: export to CSV, create fresh schema with Alembic, re-import data, validate row counts match.

### Gaps
- No specific recommendation on testing strategy for schema migrations on real data (encrypted test databases vs. production replicas). Recommend: before deploying a migration to a shared lab computer, test it on a copy of the production database.

---

## Backup, Retention, and Multi-PC/Lab Storage

### Takeaway
Implement tiered backup: local daily snapshots in %APPDATA%/backups (keep 30 days), encrypted copies to shared network drive (keep 1 year), and optional cloud sync to ARIM-mdx or NOMAD for long-term archival. Central LIMS server is not justified for small labs; network-attached storage (NAS) with automatic nightly sync is sufficient.

### Cited Findings
- (No specific citations found on backup practices for measurement software in research labs. This reflects a gap in published best practices guidance.)
- ARIM-mdx "provides interactive computing services, large-volume cloud storage, direct data transfer from experimental equipment" indicating a centralized platform is available for Japanese institutions — [ARIM-mdx Data System](https://arxiv.org/abs/2409.06734)
- NIMS DICE platform offers "Use of Facilities and Data" services for centralized management — [NIMS Use of Facilities and Data](https://www.nims.go.jp/eng/business/equipment/index.html)

### Inferences
- **Local backup (auto-daily)**: On application startup, copy `measurement.db` to `%APPDATA%/V1_TE_Measurements/backups/measurement_YYYYMMDD_HHMMSS.db`. Retention: delete files >30 days old. Purpose: recover from accidental deletion or corruption; user can restore via GUI menu.
- **Shared network backup (daily, user-triggered)**: Provide a "Backup to network drive" menu item that copies latest `.db` and all HDF5 files from today to `\\shared_server\lab_backups\V1_TE\YYYY-MM-DD\`. Encrypt path with Windows NTFS permission or WinRAR password-protect archive. Retention: 1 year. Purpose: protect against hard drive failure, enable access from other PCs.
- **ARIM-mdx / NOMAD archival (per run, optional)**: After run completion and review, provide "Archive to ARIM" button (if ARIM-mdx client is configured). Push HDF5 + metadata. Retention: indefinite on institutional platform. Purpose: FAIR data sharing, compliance with funding agency mandates.
- **Version control for code and configuration**: Store measurement app code, SQL schema migrations, calibration constants, and hardware configs in git (GitHub or institutional GitLab). This is separate from data backup but critical for reproducibility.
- For multi-PC scenarios: designate one shared-lab NAS as "measurement archive" (read-only for safety). Each measurement PC stores local copy, syncs to NAS daily via background scheduled task (Windows Task Scheduler: `robocopy` with `/XO` to skip unchanged files). All PCs read-only access to NAS so accidental deletion by one user doesn't affect others.

### Gaps
- No regulatory guidance found for academic materials labs on minimum retention period for raw thermoelectric measurement data. Recommend: check with university research office and funding agency (MEXT for Japanese labs, NSF/DOE for US labs) for their data retention policies.
- Cost-benefit analysis of cloud sync (ARIM-mdx, AWS, Azure) vs. local NAS not addressed. For Shizuoka University, ARIM-mdx is likely free/subsidized via MEXT participation; cloud commercial services (AWS S3 Glacier) may be cost-effective only if data volume exceeds 100 GB/year. Recommend: start with local NAS + ARIM-mdx, add commercial cloud only if scalability becomes an issue.

---

## Recommended Architecture Summary

### Immediate Actions (Current App Enhancement)

1. **Add Alembic for schema migration**: Replace `create_all()` with Alembic-versioned migrations; add `audit_log` table and per-run hash fields.
2. **Enable SQLite WAL mode**: Set `PRAGMA journal_mode=WAL` at connection time; handle recovery on startup.
3. **Fix "running" state persistence**: Add run state enum (running/paused/crashed/completed), detect orphaned runs at startup, resolve with user prompt.
4. **Separate raw from derived data**: Store raw (T1, T2, ΔT, V, I) as numeric columns in `data_points` table, compute Seebeck on-demand with provenance record.
5. **Add local backup**: Auto-create daily backup in %APPDATA%, retention 30 days, user-accessible restore menu.
6. **Minimal audit logging**: Insert one audit entry per 50 data points (not per row) to data_point_audit table with user, timestamp, and record ID.

### Medium-Term (Next Release)

7. **ELN integration**: Add optional eLabFTW or Kadi4Mat integration (if ARIM-mdx official recommendation received, use that). Asynchronous push-on-demand via REST API.
8. **Metadata enrichment**: Require sample geometry input (no 1×1×1 placeholders); embed operator name, software version, git hash, instrument calibration dates, settings snapshot in HDF5 NeXus attributes.
9. **Network backup**: Add menu item for user-triggered sync to shared network drive (with destination path configuration).
10. **Hash-based integrity check**: Store SHA-256 of raw data block per run, validate on re-open.

### Long-Term (Roadmap Items)

11. **NOMAD/ARIM-mdx export**: Implement serializer to convert run metadata + results to NOMAD Metainfo schema, enable one-click push to NOMAD Lab or ARIM-mdx platform.
12. **Bluesky-style event model**: Optionally export runs as Bluesky event stream (RunStart, EventDescriptor, Events, RunStop JSON-LD) for re-analysis in Jupyter or Bluesky Databroker.
13. **RO-Crate packaging**: Auto-generate RO-Crate metadata file alongside HDF5 for each run, including software version, computation provenance, sample metadata, for archival and re-executability.
14. **Quantum Design PPMS / Optris direct integration**: Standardize data import from instruments, validate against expected schemas, reject malformed data on ingest.

---

## References and Key Sources

### Standards and Ontologies
- [NeXus International Advisory Committee (NIAC)](https://www.nexusformat.org/)
- [FAIRmat / NOMAD Lab](https://fairmat-nfdi.eu/)
- [EMMO (Elementary Multiperspective Material Ontology)](https://emmc.eu/emmo/)
- [CHAMEO Domain Ontology](https://github.com/emmo-repo/domain-characterisation-methodology)
- [W3C PROV](https://www.w3.org/TR/prov-overview/)
- [RO-Crate Specification](https://w3id.org/ro/crate)

### Measurement Software Ecosystems
- [Bluesky Project Documentation](https://blueskyproject.io/)
- [QCoDeS Documentation](https://qcodes.github.io/)
- [Quantum Design PPMS Manuals](https://qdusa.com/pharosindex/)

### Electronic Lab Notebooks
- [eLabFTW](https://www.elabftw.net/)
- [Kadi4Mat](https://helmholtz.software/software/kadi4mat)
- [openBIS](https://openbis.ch/)

### Japan-Specific Data Initiatives
- [ARIM-mdx (Advanced Research Infrastructure for Materials)](https://www.nims.go.jp/eng/infrastructure/facilities/ARIM.html)
- [NIMS DICE Platform](https://dice.nims.go.jp/)

### Database and Serialization Tools
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [HDF5 and h5py](https://www.h5py.org/)
- [Zarr Documentation](https://zarr.readthedocs.io/)

### Data Integrity and Compliance
- [ALCOA+ Principles Guide](https://totallab.com/resources/alcoa-principles/)
- [SQLite Documentation (WAL, Atomic Commits)](https://www.sqlite.org/wal.html)
