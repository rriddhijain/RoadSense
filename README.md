# RoadSense: Smart Infrastructure Monitoring at Scale

**Every driver knows the pain.** Potholes damage our vehicles, waste fuel, and cost the global economy billions in repairs annually. But here's the thing—*road authorities don't know where they are either*. 

**Introducing RoadSense:** The world's first crowdsourced, hardware-agnostic road damage detection system that turns every vehicle into a sensor.

Using advanced accelerometer analysis and proprietary classification algorithms, RoadSense detects and classifies potholes and speed breakers in real-time—all from a simple embedded device no larger than a phone. No manual surveys. No guesswork. Just **live, actionable intelligence**.

---

## What We Do

### Real-Time Detection
- **Intelligent Hardware**: Firmware running on ultra-low-power microcontrollers processes accelerometer data at 200Hz, automatically classifying road anomalies into severity levels
- **Three-Tier Classification System**: Green (minor), Yellow (moderate), Red (severe) alerts—so municipal workers prioritize repairs strategically
- **Live Feedback**: RGB LED indicators provide instant driver feedback while data streams to the cloud

### Smart Dashboard & Heatmapping
- **Live Visualization**: Watch incidents happen in real-time across your city
- **Heatmap Analytics**: Geographic clustering reveals road infrastructure hotspots—the smoothness map for every street
- **Session Tracking**: Analyze routes by vehicle, driver, or time period to identify repeat problem areas
- **Data Intelligence**: Peak damage metrics, incident width, severity distribution, and trend analysis at your fingertips

---

## The Technology Stack

- **Firmware**: C-based embedded processing on TI MSPM0G3507 microcontroller
- **Host Platform**: Python-powered dashboard with Plotly visualization
- **Data Pipeline**: JSON-based event streaming with GPS integration (mock and real)
- **Edge Intelligence**: Dual-channel ADC processing with noise filtering and baseline calibration

---

## Why RoadSense Wins

**Scalable**: Deploy on any vehicle fleet—taxis, buses, delivery services, rideshare  
**Non-Intrusive**: Works with existing CAN bus or UART communication  
**Real-Time**: No cloud dependency—local processing with optional cloud sync  
**Data-Driven**: Transforms raw accelerometer noise into actionable infrastructure intelligence  
**Cost-Effective**: Leverages low-cost sensors already in vehicles  

---

## The Market Opportunity

- **Municipal Infrastructure**: $500B+ annual road maintenance market globally
- **Fleet Operations**: Insurance & logistics companies willing to pay for road condition intelligence
- **Smart City Integration**: Governments mandating IoT-based infrastructure monitoring
- **Connected Vehicles**: OEMs building in road intelligence as a premium feature

---

## What You Get

A complete, deployable system ready to revolutionize how cities understand and maintain their roads. From hardware firmware to production-grade visualization—RoadSense is the missing layer in smart transportation infrastructure.

**The roads are talking. We're listening.**

---

## Project Structure

```
firmware/        - Embedded C code for sensor processing & classification
host/            - Python dashboard for visualization & analytics
  pothole_dashboard.py  - Live Dash application with heatmaps
  pothole_logger.py     - Event logging system
  potholes.json         - Pothole event database
  speedbreakers.json    - Speed breaker event database
```

---

## Getting Started

1. **Deploy Firmware**: Flash the embedded code onto supported microcontrollers
2. **Run Logger**: Start the logging service to collect accelerometer events
3. **Launch Dashboard**: Access the live visualization dashboard on localhost
4. **Monitor & Act**: Watch real-time road damage detection with severity-based prioritization

RoadSense: *Where Infrastructure Meets Intelligence*
