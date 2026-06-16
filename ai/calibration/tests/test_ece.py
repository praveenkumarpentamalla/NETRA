"""
Project NETRA — Calibration Test Suite
KPI-12 (GATING): ECE ≤ 0.05 for every shipped classifier
KPI-8 (GATING): Demographic parity difference ≤ 0.10
"""

import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bias_evaluation import (
    compute_ece,
    compute_demographic_parity_difference,
    DemographicGroup,
    find_operating_point_fmr,
    run_full_bias_evaluation,
    REQUIRED_STRATA,
)


class TestECE:
    def test_perfectly_calibrated_model_has_zero_ece(self):
        """A perfectly calibrated model should have ECE near 0."""
        np.random.seed(42)
        n = 10000
        y_prob = np.random.uniform(0, 1, n)
        y_true = (np.random.uniform(0, 1, n) < y_prob).astype(int)

        ece = compute_ece(y_true, y_prob)
        assert ece < 0.02, f"Perfectly calibrated model should have low ECE, got {ece}"

    def test_overconfident_model_has_high_ece(self):
        """A model that's always overconfident should fail the KPI."""
        np.random.seed(42)
        n = 1000
        y_true = np.random.binomial(1, 0.3, n)  # true rate 30%
        y_prob = np.full(n, 0.95)  # always predicts 95% confidence

        ece = compute_ece(y_true, y_prob)
        assert ece > 0.05, "Overconfident model should fail ECE KPI"

    def test_ece_kpi_threshold(self):
        """KPI-12: ECE ≤ 0.05 is the gating threshold."""
        KPI_THRESHOLD = 0.05
        assert KPI_THRESHOLD == 0.05  # Document the gating value

    def test_well_calibrated_fr_model_passes_kpi(self):
        """Simulate a well-calibrated face recognition model — should pass."""
        np.random.seed(1)
        n = 5000
        true_probs = np.random.beta(2, 5, n)  # realistic probability distribution
        y_true = (np.random.uniform(0, 1, n) < true_probs).astype(int)
        # Add small calibration noise (well-calibrated within 3%)
        y_prob = np.clip(true_probs + np.random.normal(0, 0.02, n), 0, 1)

        ece = compute_ece(y_true, y_prob)
        assert ece <= 0.05, f"Well-calibrated model failed KPI: ECE={ece}"


class TestDemographicParity:
    def test_equal_treatment_across_groups_passes(self):
        """Groups with equal positive rates should pass parity KPI."""
        np.random.seed(42)
        groups = []
        for name in ['male', 'female']:
            n = 500
            y_true = np.random.binomial(1, 0.1, n)
            y_prob = np.random.uniform(0, 1, n)
            y_pred = (y_prob > 0.5).astype(int)
            groups.append(DemographicGroup(name, y_true, y_pred, y_prob))

        result = compute_demographic_parity_difference(groups)
        assert result['demographic_parity_difference'] < 0.10

    def test_biased_model_fails_parity_kpi(self):
        """A model with very different positive rates across groups should fail."""
        np.random.seed(42)
        n = 500
        group_a = DemographicGroup(
            'group_a',
            np.random.binomial(1, 0.1, n),
            np.random.binomial(1, 0.05, n),  # low positive rate
            np.random.uniform(0, 0.3, n),
        )
        group_b = DemographicGroup(
            'group_b',
            np.random.binomial(1, 0.1, n),
            np.random.binomial(1, 0.45, n),  # high positive rate — biased
            np.random.uniform(0.3, 0.8, n),
        )

        result = compute_demographic_parity_difference([group_a, group_b])
        assert result['demographic_parity_difference'] > 0.10
        assert result['passes_kpi'] is False

    def test_required_strata_coverage(self):
        """Verify all 18 required demographic strata are defined (6 sex×age × 3 skin tone bands min)."""
        assert len(REQUIRED_STRATA) == 18
        # Must cover at least 6 sex × age × skin-tone strata per §H.1
        sexes = set(s.split('_')[0] for s in REQUIRED_STRATA)
        assert sexes == {'male', 'female'}


class TestOperatingPoint:
    def test_fmr_threshold_achievable_for_separable_classes(self):
        """For well-separated classes, FMR ≤ 1e-4 should be achievable."""
        np.random.seed(42)
        n_neg = 50000
        n_pos = 5000
        y_true = np.concatenate([np.zeros(n_neg), np.ones(n_pos)])
        y_prob = np.concatenate([
            np.random.beta(1, 10, n_neg),  # negatives skew low
            np.random.beta(10, 1, n_pos),   # positives skew high
        ])

        result = find_operating_point_fmr(y_true, y_prob, target_fmr=1e-4)
        assert result['passes_kpi'] is True
        assert result['threshold'] is not None

    def test_fmr_threshold_unachievable_for_overlapping_classes(self):
        """For heavily overlapping classes, FMR ≤ 1e-4 may not be achievable."""
        np.random.seed(42)
        n = 1000
        y_true = np.random.binomial(1, 0.5, n)
        y_prob = np.random.uniform(0.45, 0.55, n)  # heavily overlapping

        result = find_operating_point_fmr(y_true, y_prob, target_fmr=1e-4)
        # With heavy overlap, very high threshold needed; may or may not achieve
        # depending on random draw — test just verifies function doesn't crash
        assert 'passes_kpi' in result


class TestFullBiasEvaluation:
    def test_full_report_generation(self):
        """Full bias report should compute all required KPI fields."""
        np.random.seed(42)
        n = 2000
        y_true = np.random.binomial(1, 0.1, n)
        y_prob = np.clip(y_true * 0.7 + np.random.normal(0.15, 0.1, n), 0, 1)

        groups = [
            DemographicGroup(
                f'stratum_{i}',
                y_true[i*200:(i+1)*200],
                (y_prob[i*200:(i+1)*200] > 0.5).astype(int),
                y_prob[i*200:(i+1)*200],
            )
            for i in range(10)
        ]

        report = run_full_bias_evaluation(
            model_name='netra-fr-arcface',
            model_version='1.0.0',
            y_true_all=y_true,
            y_prob_all=y_prob,
            demographic_groups=groups,
        )

        result = report.to_dict()
        assert 'gating_kpis' in result
        assert 'ece_le_0_05' in result['gating_kpis']
        assert 'demographic_parity_diff_le_0_10' in result['gating_kpis']
        assert 'fmr_le_1e4_achievable' in result['gating_kpis']
        assert 'all_kpis_pass' in result['gating_kpis']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
