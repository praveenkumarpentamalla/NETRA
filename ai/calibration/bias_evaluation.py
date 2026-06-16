"""
Project NETRA — Calibration & Bias Evaluation
Computes ECE, demographic parity difference, ROC/DET curves.
KPI gating: ECE ≤ 0.05, demographic parity difference ≤ 0.10.
Requires Indian-population evaluation set.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import json
import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Expected Calibration Error (ECE)
# ──────────────────────────────────────────────────────────────

def compute_ece(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 15,
) -> float:
    """
    Expected Calibration Error (equal-width bins).
    KPI: ECE ≤ 0.05 for every shipped classifier.
    """
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_true)

    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (y_prob >= lo) & (y_prob < hi)
        if mask.sum() == 0:
            continue
        bin_acc = y_true[mask].mean()
        bin_conf = y_prob[mask].mean()
        bin_size = mask.sum()
        ece += (bin_size / n) * abs(bin_acc - bin_conf)

    return float(ece)


def compute_calibration_plot(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> Dict:
    """Returns data for reliability diagram (fraction_of_positives vs mean_predicted)."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    fractions, means = [], []

    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (y_prob >= lo) & (y_prob < hi)
        if mask.sum() == 0:
            continue
        fractions.append(float(y_true[mask].mean()))
        means.append(float(y_prob[mask].mean()))

    return {"fraction_of_positives": fractions, "mean_predicted_value": means}


# ──────────────────────────────────────────────────────────────
# Demographic Parity & Fairness
# ──────────────────────────────────────────────────────────────

@dataclass
class DemographicGroup:
    name: str
    y_true: np.ndarray
    y_pred: np.ndarray
    y_prob: np.ndarray


def compute_demographic_parity_difference(
    groups: List[DemographicGroup],
) -> Dict:
    """
    Compute demographic parity difference across groups.
    KPI: max difference ≤ 0.10 across sex, age band, skin tone.

    Demographic Parity: P(ŷ=1 | group=A) ≈ P(ŷ=1 | group=B)
    """
    positive_rates = {g.name: float(g.y_pred.mean()) for g in groups}
    rates = list(positive_rates.values())
    max_diff = max(rates) - min(rates)

    group_ecse = {
        g.name: compute_ece(g.y_true, g.y_prob)
        for g in groups
    }

    # Equal Opportunity Difference (True Positive Rate parity)
    tpr = {}
    for g in groups:
        pos_mask = g.y_true == 1
        if pos_mask.sum() > 0:
            tpr[g.name] = float(g.y_pred[pos_mask].mean())
        else:
            tpr[g.name] = 0.0

    tpr_values = list(tpr.values())
    eod = max(tpr_values) - min(tpr_values) if tpr_values else 0.0

    return {
        "positive_rates": positive_rates,
        "demographic_parity_difference": max_diff,
        "equal_opportunity_difference": eod,
        "per_group_ece": group_ecse,
        "passes_kpi": max_diff <= 0.10 and eod <= 0.10,
        "kpi_threshold": 0.10,
    }


# ──────────────────────────────────────────────────────────────
# ROC / DET curves
# ──────────────────────────────────────────────────────────────

def compute_roc_curve(y_true: np.ndarray, y_prob: np.ndarray) -> Dict:
    """Compute ROC curve points (FPR, TPR) and AUC."""
    thresholds = np.linspace(0, 1, 200)[::-1]
    fpr_list, tpr_list = [1.0], [1.0]

    n_pos = (y_true == 1).sum()
    n_neg = (y_true == 0).sum()

    for t in thresholds:
        y_pred = (y_prob >= t).astype(int)
        tp = ((y_pred == 1) & (y_true == 1)).sum()
        fp = ((y_pred == 1) & (y_true == 0)).sum()
        tpr = tp / n_pos if n_pos > 0 else 0.0
        fpr = fp / n_neg if n_neg > 0 else 0.0
        fpr_list.append(float(fpr))
        tpr_list.append(float(tpr))

    fpr_list.append(0.0)
    tpr_list.append(0.0)

    # AUC via trapezoidal rule
    auc = float(np.trapz(tpr_list[::-1], fpr_list[::-1]))

    return {
        "fpr": fpr_list,
        "tpr": tpr_list,
        "auc": round(auc, 4),
        "thresholds": thresholds.tolist(),
    }


def find_operating_point_fmr(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    target_fmr: float = 1e-4,
) -> Dict:
    """
    Find threshold that achieves FMR (False Match Rate) ≤ target_fmr.
    KPI: FMR ≤ 1e-4 on Indian-population eval set.
    """
    # FMR = FPR in face recognition context
    thresholds = np.linspace(0, 1, 10000)[::-1]
    n_neg = (y_true == 0).sum()
    n_pos = (y_true == 1).sum()

    best_threshold = None
    best_fnmr = 1.0

    for t in thresholds:
        y_pred = (y_prob >= t).astype(int)
        fp = ((y_pred == 1) & (y_true == 0)).sum()
        fn = ((y_pred == 0) & (y_true == 1)).sum()
        fmr = fp / n_neg if n_neg > 0 else 0.0
        fnmr = fn / n_pos if n_pos > 0 else 0.0

        if fmr <= target_fmr:
            best_threshold = t
            best_fnmr = fnmr
            break

    return {
        "target_fmr": target_fmr,
        "threshold": float(best_threshold) if best_threshold is not None else None,
        "fnmr_at_threshold": round(float(best_fnmr), 6),
        "passes_kpi": best_threshold is not None,
    }


# ──────────────────────────────────────────────────────────────
# Full Bias Report
# ──────────────────────────────────────────────────────────────

@dataclass
class BiasReport:
    model_name: str
    model_version: str
    eval_set: str
    n_samples: int
    overall_ece: float
    ece_passes_kpi: bool
    demographic_parity: Dict
    roc: Dict
    operating_point: Dict
    per_group_results: Dict
    summary: str = field(default="")

    def to_dict(self) -> Dict:
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "eval_set": self.eval_set,
            "n_samples": self.n_samples,
            "overall_ece": round(self.overall_ece, 6),
            "ece_passes_kpi": self.ece_passes_kpi,
            "demographic_parity": self.demographic_parity,
            "roc": {
                "auc": self.roc["auc"],
                "curve_points": len(self.roc["fpr"]),
            },
            "operating_point_fmr_1e4": self.operating_point,
            "per_group_results": self.per_group_results,
            "gating_kpis": {
                "ece_le_0_05": self.ece_passes_kpi,
                "demographic_parity_diff_le_0_10": self.demographic_parity.get("passes_kpi", False),
                "fmr_le_1e4_achievable": self.operating_point.get("passes_kpi", False),
                "all_kpis_pass": (
                    self.ece_passes_kpi
                    and self.demographic_parity.get("passes_kpi", False)
                    and self.operating_point.get("passes_kpi", False)
                ),
            },
            "summary": self.summary,
        }

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Bias report saved: {path}")


def run_full_bias_evaluation(
    model_name: str,
    model_version: str,
    y_true_all: np.ndarray,
    y_prob_all: np.ndarray,
    demographic_groups: List[DemographicGroup],
    eval_set_name: str = "Indian-population-eval-v1",
) -> BiasReport:
    """
    Run complete bias evaluation per §H requirements.
    Western-only benchmarks (LFW, MegaFace) are not accepted for shipping decisions.
    """
    n = len(y_true_all)
    y_pred_all = (y_prob_all >= 0.5).astype(int)

    overall_ece = compute_ece(y_true_all, y_prob_all)
    dp = compute_demographic_parity_difference(demographic_groups)
    roc = compute_roc_curve(y_true_all, y_prob_all)
    op = find_operating_point_fmr(y_true_all, y_prob_all, target_fmr=1e-4)

    per_group = {}
    for g in demographic_groups:
        per_group[g.name] = {
            "n": len(g.y_true),
            "ece": round(compute_ece(g.y_true, g.y_prob), 6),
            "positive_rate": round(float(g.y_pred.mean()), 4),
            "roc_auc": round(compute_roc_curve(g.y_true, g.y_prob)["auc"], 4),
        }

    all_pass = (
        overall_ece <= 0.05
        and dp.get("passes_kpi", False)
        and op.get("passes_kpi", False)
    )

    summary = (
        f"Model {model_name} v{model_version} evaluated on {eval_set_name} "
        f"(n={n}). ECE={overall_ece:.4f} ({'PASS' if overall_ece<=0.05 else 'FAIL'}). "
        f"Demographic parity diff={dp['demographic_parity_difference']:.4f} "
        f"({'PASS' if dp.get('passes_kpi') else 'FAIL'}). "
        f"FMR≤1e-4 achievable: {op.get('passes_kpi', False)}. "
        f"Overall: {'✅ ALL KPIs PASS — CLEARED FOR DEPLOYMENT' if all_pass else '❌ KPI FAILURE — CANNOT SHIP'}"
    )

    return BiasReport(
        model_name=model_name,
        model_version=model_version,
        eval_set=eval_set_name,
        n_samples=n,
        overall_ece=overall_ece,
        ece_passes_kpi=overall_ece <= 0.05,
        demographic_parity=dp,
        roc=roc,
        operating_point=op,
        per_group_results=per_group,
        summary=summary,
    )


# ──────────────────────────────────────────────────────────────
# Required demographic strata for NETRA evaluation
# ──────────────────────────────────────────────────────────────

REQUIRED_STRATA = [
    # Sex × Age band × Skin tone (Monk scale MST-1 to MST-10)
    # Minimum 200 subjects per stratum for FR
    "female_18-30_MST1-3",
    "female_18-30_MST4-6",
    "female_18-30_MST7-10",
    "female_31-50_MST1-3",
    "female_31-50_MST4-6",
    "female_31-50_MST7-10",
    "female_51+_MST1-3",
    "female_51+_MST4-6",
    "female_51+_MST7-10",
    "male_18-30_MST1-3",
    "male_18-30_MST4-6",
    "male_18-30_MST7-10",
    "male_31-50_MST1-3",
    "male_31-50_MST4-6",
    "male_31-50_MST7-10",
    "male_51+_MST1-3",
    "male_51+_MST4-6",
    "male_51+_MST7-10",
]

ANPR_STRATA = [
    # Script × Condition × Illumination
    "latin_clean_day",
    "latin_clean_night",
    "latin_occluded_day",
    "latin_occluded_night",
    "devanagari_clean_day",
    "devanagari_clean_night",
    "tamil_clean_day",
    "bengali_clean_day",
    "kannada_clean_day",
]
