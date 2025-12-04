# RoadSense - Pothole and Speed Bump Detector

## Example Summary

RoadSense is an embedded application designed for the MSPM0G3507 LaunchPad that detects road anomalies such as potholes and speed bumps using an analog sensor (e.g., accelerometer or suspension displacement sensor) connected to the ADC.

The application continuously monitors the sensor data and uses a state machine to identify specific signatures:
*   **Potholes:** Detected as a "down-first" deviation (voltage drop) followed by a recovery.
*   **Speed Bumps:** Detected as an "up-first" deviation (voltage spike) followed by a recovery.

When an event is detected, the system:
1.  Classifies the severity (Green/Yellow/Red).
2.  Indicates the event using the onboard RGB LED.
3.  Transmits a JSON object over UART containing event details (type, severity, peak magnitude, timestamp, and mock GPS coordinates).

## Peripherals & Pin Assignments

| Peripheral | Pin | Function |
| --- | --- | --- |
| **ADC1** | **PB18** | Analog Input (Sensor) |
| **UART0** | **PA10** | UART TX (JSON Output) |
| **UART0** | **PA11** | UART RX |
| **GPIO** | **PB26** | User LED 2 (Red) |
| **GPIO** | **PB27** | User LED 3 (Green) |
| **GPIO** | **PB22** | User LED 1 (Blue) |
| **DEBUGSS** | **PA20** | SWCLK |
| **DEBUGSS** | **PA19** | SWDIO |

## BoosterPacks, Board Resources & Jumper Settings

Visit [LP_MSPM0G3507](https://www.ti.com/tool/LP-MSPM0G3507) for LaunchPad information, including user guide and hardware files.

### LED Indicators
The RGB LED is used to visually indicate detected events:
*   **Green:** Low severity pothole.
*   **Yellow:** Medium severity pothole.
*   **Red:** High severity pothole.
*   **White:** Speed bump detected.

## Example Usage

1.  **Setup:** Connect an analog sensor (0V - 3.3V) to pin **PB18**. Ideally, the sensor should sit at a baseline voltage (e.g., 1.65V) when the vehicle is stationary.
2.  **Monitor:** Connect the LaunchPad to a PC via USB. Open a serial terminal (115200 baud, 8N1) to view the JSON output.
3.  **Run:** Compile, load, and run the example.
4.  **Trigger:** Simulate road events by varying the sensor voltage:
    *   Quickly drop the voltage below the baseline to simulate a pothole.
    *   Quickly raise the voltage above the baseline to simulate a speed bump.

### JSON Output Format
The application outputs newline-delimited JSON objects:

**Pothole:**
```json
{"type":"POTHOLE","severity":2,"peak_mV":650,"width":45,"timestamp":12345,"x":12,"y":12}
```

**Speed Bump:**
```json
{"type":"SPEEDBRK","peak_mV":500,"width":60,"timestamp":67890,"x":15,"y":15}
```

## Application Design Details

The application uses `ADC12_0` to sample the sensor at 200Hz. A sliding window smoothing algorithm (`ALPHA_SMOOTH_Q15`) tracks the baseline voltage. Deviations from this baseline trigger the detection logic.

*   **Idle State:** Monitors for deviations exceeding `START_THR_MV`.
*   **Tracking State:** Records the peak magnitude and duration of the event.
*   **Wait Stable:** Waits for the signal to return to the baseline range (`SETTLE_THR_MV`).
*   **Refractory:** A brief pause after an event to prevent double counting.

A mock GPS module increments coordinates every second to simulate vehicle movement.
