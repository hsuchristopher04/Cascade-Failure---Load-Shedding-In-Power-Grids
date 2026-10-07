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

## Running the Code

```bash
pip install -r requirements.txt

# Full analysis for one case (about 1.5 minutes each)
python run_analysis.py --case case118
python run_analysis.py --case case300

# Both cases plus the alpha/min_base_loading sensitivity sweep (much slower)
python run_analysis.py --case all --sweep

# Run the tests
pytest
```

Results (CSVs and plots) are written to `results/<case>/`.

The simulation code lives in the `clf/` package:

- `clf/grid.py`: loads IEEE cases and builds bus graphs (lines and transformers)
- `clf/cascade.py`: cascade simulation and load-shed calculation
- `clf/analysis.py`: correlations, top-k overlap, and the sensitivity sweep

**Note:** `clf/` fixes two issues in the original notebook code. The graph now includes
transformers (previously the case118 and case300 graphs split into 6 and 78 disconnected
pieces), and load shed now counts loads cut off from the slack bus (previously the baseline,
with nothing tripped, already showed 4.3% shed for case118 and 16.8% for case300).
Because of this, numbers from `run_analysis.py` differ from the notebooks and the final report.

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

These results come from `python run_analysis.py --case all` (`alpha=0.2`, `min_base_loading=0.1`)
and are taken from `results/<case>/node_metric_summary.csv` and `edge_metric_summary.csv`.
"Load shed" is percent of total load; "cascade size" is the number of branches (lines and transformers) out of service at the end, including the initial outage.
They replace the findings from the original notebook code (see the note above).

### Case118
- Power flow failed to converge for 2 of 173 line outages and 2 of 118 bus outages; these are excluded from the correlations
- All node metrics are weak predictors of simulated severity (every correlation is below 0.35)
- Node degree is the strongest node metric, for both load shed (Pearson 0.29, Spearman 0.33) and cascade size (Pearson 0.22, Spearman 0.25)
- Node betweenness is second for load shed (Pearson 0.24, Spearman 0.22) but is close to zero for cascade size (Pearson 0.06, Spearman 0.13)
- Closeness and eigenvector centrality are close to zero for load shed and slightly negative for cascade size (Spearman -0.13 and -0.20)
- Edge betweenness shows no relationship with either load shed or cascade size (all correlations between -0.07 and 0)
- The 10 buses ranked highest by any metric share at most 3 buses with the 10 worst by load shed, and at most 2 with the 10 worst by cascade size

### Case300
- **Power flow failed to converge for 130 of 283 line outages and 133 of 300 bus outages.** These are excluded from the correlations, so the results below cover only the 153 line and 167 bus outages that converged. The excluded outages may not be representative, so treat these numbers with caution
- Node degree and node betweenness perform about equally well, and best among node metrics, for cascade size (Spearman 0.41 and 0.39, Pearson 0.29 for both)
- For load shed they are weaker (degree: Pearson 0.20, Spearman 0.31; betweenness: Pearson 0.14, Spearman 0.26)
- Node betweenness has the best top-10 match for load shed: 8 of its 10 highest-ranked buses are among the 10 worst by load shed. For cascade size, no metric matches more than 2 of 10
- Eigenvector centrality is negatively rank-correlated with severity (Spearman -0.23 for load shed, -0.30 for cascade size)
- Edge betweenness has Pearson 0.33 with cascade size and 0.19 with load shed, but Spearman only 0.13 and 0.05, so the linear relationship appears to depend on a small number of outages

### Overall
- No graph metric is a strong predictor of cascade severity in either case; the largest correlation is 0.41 (degree vs. cascade size in case300)
- Node degree is the most consistent predictor across both cases and both outcomes; closeness and eigenvector centrality are the weakest
- The metrics' top-10 rankings mostly differ from the 10 most severe outages, with the one exception of node betweenness vs. load shed in case300
- Because almost half of the case300 outages are excluded, these results do not show whether topology is more or less predictive in the larger grid
- Structural importance alone is not enough to identify the most dangerous failures; simulation remains necessary

---

## Repository Contents

```
.
├── clf/                                         # Simulation and analysis package
│   ├── __init__.py
│   ├── analysis.py                              # Correlations, top-k overlap, sensitivity sweep
│   ├── cascade.py                               # Cascade simulation and load-shed calculation
│   └── grid.py                                  # Loads IEEE cases and builds bus graphs
├── tests/                                       # pytest tests for clf/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_cascade.py
│   └── test_grid.py
├── run_analysis.py                              # Command-line entry point; writes results/<case>/
├── requirements.txt
├── pytest.ini
├── cascading_load_failure.py                    # Early script that prints the case118 network tables
├── clf-case118.ipynb                            # Original analysis on the IEEE 118-bus system
├── clf-case300.ipynb                            # Original analysis on the IEEE 300-bus system
├── figures/                                     # Plots from the notebooks
├── related-papers/                              # Background literature
├── CLF-Final-Report.pdf
├── final.pdf
├── Graph Mining Project Proposal.pdf
├── Graph Mining Project Update.pdf
├── Graph Mining Project Results.pdf
├── Graph-Mining-Project-Final-Presentation.pdf
├── project-proposal-pdf.pdf
├── update.pdf
└── README.md
```

