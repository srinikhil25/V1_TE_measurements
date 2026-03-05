## TE Measurement System — Hardware-to-Desktop Overview

**Ikeda-Hamasaki Laboratory**  
Version 1.0 — March 2026

---

## 1. End-to-End Overview

This document gives a **single high-level view from physical hardware up to the `desktop_qt` PyQt6 application**.  
It is meant to complement `DESKTOP_QT_ARCHITECTURE.md` (which focuses on the desktop app internals).

---

## 2. Layered Architecture Diagram

The following diagram shows the complete stack, from the thermoelectric sample and sensors through the instruments, PC, and finally the desktop application and database.

```mermaid
graph TD

    %% --- Physical Layer ---
    subgraph Phys["Physical / Experiment Layer"]
        SAMPLE["TE Sample\n(pellet / module)"]
        HOT_COLD["Hot & Cold Blocks\n(Peltier / heater + sink)"]
        SENSORS["Thermocouples & Voltage Leads"]
        IR_TARGET["Sample Surface / Fixture\n(IR field-of-view)"]
    end

    %% --- Instrument Layer ---
    subgraph Instr["Instrument Layer (Bench Instruments)"]
        K2700["Keithley 2700\nSwitch / DMM"]
        K2182["Keithley 2182A\nNanovoltmeter"]
        PK160["PK160 / Power Supply\n(current drive)"]
        K6221["(Optional) Keithley 6221\nAC/DC current source"]
    end

    %% --- IR Camera Layer ---
    subgraph IR["IR Camera Layer"]
        IRCAM["Optris IR Camera\n(PI / Xi series)"]
    end

    %% --- PC & OS Layer ---
    subgraph PC["Measurement PC"]
        OS["Windows OS\n(Instrument Workstation)"]
        GPIB["GPIB / USB-GPIB Adapter\n(PyVISA stack)"]
        USB["USB 2.0/3.0\n(Direct to IR camera)"]
    end

    %% --- Desktop Application Layer ---
    subgraph App["desktop_qt Desktop Application"]
        subgraph QtUI["PyQt6 UI"]
            LOGIN["LoginWindow"]
            MAINWIN["MainWindow\n+ Sidebar + Pages"]
            PAGE_SEEBECK["SeebeckPage"]
            PAGE_IV["IVPage"]
            PAGE_HISTORY["HistoryPage"]
            PAGE_SETTINGS["SettingsPage"]
        end

        subgraph Services["Application Services"]
            AUTH["AuthService"]
            MEAS_SVC["SeebeckService / IV Service"]
            IR_SVC["IrCameraService"]
        end

        subgraph InstrumentsSW["Instrument Control (Python)"]
            SMGR["MeasurementSessionManager\n(Seebeck loop thread)"]
            SYS["SeebeckSystem\n(instrument drivers)"]
        end

        subgraph IRWorker["IR Worker Subprocess"]
            IR_PROC["ir_camera_worker.py"]
            IR_SDK["Optris SDK\n(OTC / pyOptris)"]
        end

        subgraph DB["Local Data Storage"]
            SQLITE["SQLite DB\nte_measurement.db"]
        end
    end

    %% --- Physical to Instruments ---
    SAMPLE --> HOT_COLD
    HOT_COLD --> SENSORS
    SENSORS --> K2700
    SENSORS --> K2182
    HOT_COLD --> PK160
    HOT_COLD --> K6221
    IR_TARGET --> IRCAM

    %% --- Instruments to PC ---
    K2700 --> GPIB
    K2182 --> GPIB
    PK160 --> GPIB
    K6221 --> GPIB
    GPIB --> OS

    IRCAM --> USB
    USB --> OS

    %% --- OS to Application ---
    OS --> QtUI
    OS --> InstrumentsSW
    OS --> IRWorker
    OS --> SQLITE

    %% --- Application Internal Flows ---
    LOGIN --> AUTH
    AUTH --> SQLITE
    AUTH --> MAINWIN

    MAINWIN --> PAGE_SEEBECK
    MAINWIN --> PAGE_IV
    MAINWIN --> PAGE_HISTORY
    MAINWIN --> PAGE_SETTINGS

    PAGE_SEEBECK --> MEAS_SVC
    PAGE_IV --> MEAS_SVC

    MEAS_SVC --> SMGR
    SMGR --> SYS
    SYS --> GPIB

    PAGE_SEEBECK --> IR_SVC
    IR_SVC --> IR_PROC
    IR_PROC --> IR_SDK
    IR_PROC --> IR_SVC

    PAGE_HISTORY --> SQLITE
    MEAS_SVC --> SQLITE
    SMGR --> SQLITE
```

---

## 3. Presentation-Style Overview Diagram

This diagram is a simplified, left-to-right view that matches the slide-style layout you showed.  
Use it as a reference when placing labels on your graphics.

```mermaid
graph LR

    CSRC["Current source (PK160 / 6221)"]
    WAVE["Programmable current waveform"]
    SAMPLE["TE sample + hot/cold blocks\nThermocouples (T_hot, T_cold) + Voltage leads (ΔV)"]

    INSTR["Bench instruments\nKeithley 2700 / 2182A / PK160 / 6221"]
    GPIB["GPIB bus (PyVISA)"]

    IRCAM["Optris IR camera"]
    IRSDK["Optris Direct SDK"]

    PC["Measurement PC (Windows)\nGPIB / USB drivers"]

    APP["desktop_qt desktop application\nPyQt6 UI + Seebeck measurement service\nLive plots + IR viewer + history"]

    DB["Local database\nSQLite – te_measurement.db"]

    CSRC --> WAVE
    WAVE --> SAMPLE

    SAMPLE --> INSTR
    INSTR --> GPIB
    GPIB --> PC

    SAMPLE --> IRCAM
    IRCAM --> IRSDK
    IRSDK --> PC

    PC --> APP
    APP --> DB
```

---

## 4. Layer Descriptions

- **Physical / Experiment Layer**  
  Real-world hardware: thermoelectric sample, hot/cold blocks, and the thermocouples / voltage leads that sense temperatures and TE voltage. The IR camera observes the sample fixture to give a spatial temperature map.

- **Instrument Layer**  
  Bench instruments (Keithley 2182A, 2700, PK160, optional 6221) apply current and measure temperatures and thermoelectric voltage. They expose SCPI-style command interfaces over GPIB, which are abstracted by the `SeebeckSystem` driver in the desktop app.

- **IR Camera Layer**  
  The Optris IR camera provides time-synchronized thermal images for the sample region. It is controlled via the vendor SDK from an isolated subprocess to protect the main UI from DLL/COM crashes.

- **Measurement PC & OS Layer**  
  A dedicated Windows PC hosts the GPIB adapter and the USB-connected IR camera. PyVISA and the Optris SDKs are installed here. The `desktop_qt` Python environment runs entirely on this machine with no external network dependency.

- **Desktop Application Layer (`desktop_qt`)**  
  The PyQt6 application provides login, Seebeck and I–V measurement workflows, live plots, IR live view, and history export. Services such as `SeebeckService`, `MeasurementSessionManager`, and `IrCameraService` mediate between the UI and the instrument/IR layers.

- **Data Storage Layer (SQLite)**  
  All measurements, per-sample rows, integrity hashes, users, and labs are stored in a local SQLite database (`te_measurement.db` under `%APPDATA%`). The same schema and SQLAlchemy models are used across the desktop application.

---

## 5. How This Relates to Seebeck Measurements

During a Seebeck run:

- The **SeebeckPage** configures the current waveform and sample metadata.
- `SeebeckService` and `MeasurementSessionManager` translate this into a 1-second control loop that drives current via the instrument layer and acquires temperatures and TEMF.
- Each time step is committed to **SQLite**, and the desktop app simultaneously updates live plots such as **Seebeck coefficient vs. \(T_0\)** (the type of graph shown in your exports).
- The IR worker subprocess continuously streams frames to the UI so that thermal behavior can be correlated with the numerical Seebeck data.

