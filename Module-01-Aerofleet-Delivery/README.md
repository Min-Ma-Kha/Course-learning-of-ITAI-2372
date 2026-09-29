# Aerofleet Delivery: Process Mapping for AI Integration

**ITAI 2372 · Module 01 assignment: Process Mapping for AI Integration**
**Author:** Min Ma Kha
**Industry:** Logistics (last-mile drone delivery)

Aerofleet Delivery flies small retail orders from a store's drone hub to a designated drop zone in the customer's yard, with a 30-minute delivery target. This project maps that workflow using the Input → Process → Decision → Action → Outcome framework and identifies where AI adds value, and where a human must stay in the loop.

## Files

| File | What it is |
|---|---|
| `Aerofleet_Delivery.pptx` | 3-slide presentation: business context, process map, AI integration analysis |
| `aerofleet_delivery_process_map.mermaid` | Mermaid source for the process map (open in [mermaid.live](https://mermaid.live)) |

## Process map

Green = AI step or decision · Orange = human-in-the-loop · Light blue = system step

```mermaid
%%{init: {"theme": "base", "themeVariables": {"background": "#ffffff", "fontFamily": "Arial", "fontSize": "16px", "lineColor": "#5B6B76"}}}%%
flowchart TD
    IN(["INPUT<br/>Order received,<br/>drop spot chosen"]):::system
    D1{"D1 · AI<br/>Weight, range, and<br/>drop spot OK?"}:::ai
    VAN["ACTION<br/>Deliver by van instead"]:::system
    PK["PROCESS · Human<br/>Associate picks, packs,<br/>and attaches the order"]:::human
    D2{"D2 · Human<br/>Package secured<br/>and balanced?"}:::human
    RP["ACTION · Human<br/>Repack the order"]:::human
    D3{"D3 · AI<br/>Safe to fly?<br/>Weather and limits"}:::ai
    HOLD["ACTION<br/>Hold the order,<br/>or send by van"]:::system
    D4{"D4 · AI<br/>Route clear of<br/>other drones?"}:::ai
    RR["ACTION · AI<br/>Reroute or delay<br/>(shared flight plans)"]:::ai
    LA["ACTION · AI<br/>Drone launches<br/>on its route"]:::ai
    OV["OVERSIGHT · Human<br/>Operator can take<br/>over any flight"]:::human
    D5{"D5 · AI<br/>Is the drop<br/>zone clear?"}:::ai
    D6{"D6 · Human<br/>Safety override:<br/>go, retry, or abort?"}:::human
    AB["ACTION<br/>Abort and<br/>return to hub"]:::system
    LW["ACTION<br/>Package lowered on tether;<br/>delivery photo taken"]:::system
    D7{"D7 · AI<br/>Clean drop on the<br/>chosen spot?"}:::ai
    D8{"D8 · Human<br/>Refund, redeliver,<br/>or recover?"}:::human
    RB["ACTION · AI<br/>Drone flies back<br/>to recharge"]:::ai
    OUT(["OUTCOME<br/>Package delivered<br/>to the correct zone"]):::system

    IN --> D1
    D1 -->|Yes| PK
    D1 -->|No| VAN
    PK --> D2
    D2 -->|Yes| D3
    D2 -->|No| RP
    RP --> D2
    D3 -->|Yes| D4
    D3 -->|No| HOLD
    D4 -->|Yes| LA
    D4 -->|No| RR
    RR --> D4
    OV -.->|if needed| LA
    LA --> D5
    D5 -->|Yes| LW
    D5 -->|"No or unsure"| D6
    D6 -->|Go| LW
    D6 -.->|Retry| D5
    D6 -->|Abort| AB
    LW --> D7
    D7 -->|Yes| RB
    D7 -->|"No, or customer reports a problem"| D8
    RB --> OUT

    classDef ai fill:#E3F2EA,stroke:#2E8B57,stroke-width:2px,color:#14304D
    classDef human fill:#FDE3CC,stroke:#D0701F,stroke-width:2px,color:#14304D
    classDef system fill:#E6EFF6,stroke:#7F9DB5,stroke-width:1.5px,color:#14304D
```

## AI integration summary

**Where AI fits**
- **D3 · Forecasting and rule checks:** weather and flight limits, checked in the seconds before launch.
- **D4 · Real-time routing:** operators share flight plans and routes adjust automatically.
- **D5 · Computer vision:** detects people, pets, and objects in the drop zone.
- **D7 · Telemetry validation:** confirms the exact drop coordinates with RTK GPS.

**Where AI does not fully fit**
- **D2 · Packing check:** securing and balancing a package is hands-on work.
- **D6 · Safety override:** nuanced visual judgment (lawn ornament vs. pet) and final safety accountability.
- **D8 · Customer problems:** needs empathy and judgment about whether a claim is genuine.

**Data requirements:** real-time weather feeds, live UTM air-traffic data and flight plans, RTK GPS telemetry and battery logs, residential image datasets for object detection, delivery photos and customer claims.

## Sources

- Chain Store Age: [Walmart builds drone delivery capability in Greater Houston](https://chainstoreage.com/walmart-builds-drone-delivery-capability-greater-houston)
- DroneXL: [Walmart and Wing launch drone delivery in Houston](https://dronexl.co/2026/01/16/walmart-wing-drone-delivery-houston/) (January 2026)
- Dronelife: [Flytrex and Wing report zero airspace conflicts](https://dronelife.com/2026/06/25/flytrex-and-wing-report-zero-airspace-conflicts-for-multi-operator-drone-delivery/) (June 2026)
- FAA: proposed 14 CFR Part 108, Normalizing Unmanned Aircraft Systems Beyond Visual Line of Sight Operations (NPRM, August 2025)
