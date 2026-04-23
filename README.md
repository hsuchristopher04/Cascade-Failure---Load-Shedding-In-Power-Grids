# Cascade Failure and Load Shedding in Power Grids

This project studies how well graph-based network metrics predict cascade severity in electric power systems.

Using IEEE test cases from `pandapower`, I build graph representations of the grid, compute node and edge centrality metrics, and compare those structural measures against simulation-based cascade outcomes such as load shed and cascade size.

The main goal is to answer:

- Which nodes and edges are most critical under cascade dynamics?
- How well do graph metrics such as degree and betweenness predict true criticality?
- How sensitive are the results to overload threshold calibration?
- Do these relationships change between smaller and larger grid models?

---

## Project Overview

The workflow combines:

1. **Power system modeling** using `pandapower`
2. **Graph construction** from bus-line connectivity
3. **Centrality analysis** on nodes and edges
4. **Cascade simulation** using iterative line-tripping logic
5. **Comparative analysis** between graph metrics and simulation impact
6. **Threshold calibration / sensitivity analysis**
7. **Validation on multiple systems** (`case118` and `case300`)

---

## Main Datasets

This project uses standard IEEE benchmark networks provided through `pandapower`:

- **IEEE 118-bus system**
- **IEEE 300-bus system**

---

## Methods

### Graph-Based Metrics
For each network, I compute structural metrics including:

- Node degree
- Node betweenness centrality
- Closeness centrality
- Eigenvector centrality
- Edge betweenness centrality

### Cascade Model
For each contingency, the simulation:

1. Removes an initial transmission line or node-triggered set of incident lines
2. Runs AC power flow using `pandapower`
3. Computes post-contingency line loadings
4. Trips lines whose loading exceeds a baseline-relative overload threshold
5. Repeats until no new trips occur or the solver fails
6. Measures final impact using:
   - Cascade size
   - Load shed (MW)
   - Load shed (%)
   - Largest connected component (LCC) size

### Threshold Calibration
I also evaluate how results change under different overload settings by sweeping:

- `alpha` (relative overload margin)
- `min_base_loading` (floor for near-zero baseline lines)

---

## Key Findings

### Case118
- Node degree was generally a stronger predictor of simulation impact than node betweenness
- Edge betweenness was weak for predicting cascade severity
- Several low-degree buses still caused high load shed
- Graph-based importance and simulation-based criticality did **not** fully align

### Case300
- Correlations between node metrics and simulation impact were much stronger
- Node degree became the strongest overall predictor
- Larger-network structure appeared to be more informative for cascade severity
- Topology was more predictive in `case300` than in `case118`

### Overall
- Not all graph metrics capture criticality equally well
- Structural importance alone is not enough to identify the most dangerous failures
- Simulation remains necessary, especially for smaller or less structurally regular networks

---

## Repository Contents

```text
.
├── cascading_load_failure.py
├── clf.ipynb
├── Graph Mining Project Proposal.pdf
├── Graph Mining Project Results.pdf
├── Graph-Mining-Project-Final-Presentation.pdf
├── final.pdf
└── README.md

