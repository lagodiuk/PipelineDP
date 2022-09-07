# Copyright 2022 OpenMined.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""UtilityAnalysisEngine Test"""
import unittest
import copy

import pipeline_dp
from pipeline_dp import budget_accounting
from utility_analysis_new import dp_engine


class DpEngine(unittest.TestCase):

    def _get_default_extractors(self) -> pipeline_dp.DataExtractors:
        return pipeline_dp.DataExtractors(
            privacy_id_extractor=lambda x: x,
            partition_extractor=lambda x: x,
            value_extractor=lambda x: x,
        )

    def test_utility_analysis_params(self):
        default_extractors = self._get_default_extractors()
        default_params = pipeline_dp.AggregateParams(
            noise_kind=pipeline_dp.NoiseKind.GAUSSIAN,
            max_partitions_contributed=1,
            max_contributions_per_partition=1,
            metrics=[pipeline_dp.Metrics.COUNT])
        params_with_custom_combiners = copy.copy(default_params)
        params_with_custom_combiners.custom_combiners = sum
        params_with_unsupported_metric = copy.copy(default_params)
        params_with_unsupported_metric.metrics = [pipeline_dp.Metrics.MEAN]
        params_with_contribution_bounds_already_enforced = default_params
        params_with_contribution_bounds_already_enforced.contribution_bounds_already_enforced = True

        test_cases = [
            {
                "desc": "custom combiners",
                "params": params_with_custom_combiners,
                "data_extractor": default_extractors,
                "public_partitions": [1]
            },
            {
                "desc": "unsupported metric in metrics",
                "params": params_with_unsupported_metric,
                "data_extractor": default_extractors,
                "public_partitions": [1]
            },
            {
                "desc": "contribution bounds are already enforced",
                "params": params_with_contribution_bounds_already_enforced,
                "data_extractor": default_extractors,
                "public_partitions": [1]
            },
        ]

        for test_case in test_cases:

            with self.assertRaisesRegex(Exception,
                                        expected_regex=test_case["desc"]):
                budget_accountant = budget_accounting.NaiveBudgetAccountant(
                    total_epsilon=1, total_delta=1e-10)
                engine = dp_engine.UtilityAnalysisEngine(
                    budget_accountant=budget_accountant,
                    backend=pipeline_dp.LocalBackend())
                col = [0, 1, 2]
                engine.aggregate(
                    col,
                    test_case["params"],
                    test_case["data_extractor"],
                    public_partitions=test_case["public_partitions"])

    def test_aggregate_public_partition_e2e(self):
        # Arrange
        aggregator_params = pipeline_dp.AggregateParams(
            noise_kind=pipeline_dp.NoiseKind.GAUSSIAN,
            metrics=[pipeline_dp.Metrics.COUNT],
            max_partitions_contributed=1,
            max_contributions_per_partition=1)

        budget_accountant = pipeline_dp.NaiveBudgetAccountant(total_epsilon=1,
                                                              total_delta=1e-10)

        public_partitions = ["pk0", "pk1", "pk101"]

        # Input collection has 100 elements, such that each privacy id
        # contributes 1 time and each partition has 1 element.
        col = list(range(100))
        data_extractor = pipeline_dp.DataExtractors(
            privacy_id_extractor=lambda x: x,
            partition_extractor=lambda x: f"pk{x}",
            value_extractor=lambda x: None)

        engine = dp_engine.UtilityAnalysisEngine(
            budget_accountant=budget_accountant,
            backend=pipeline_dp.LocalBackend())

        col = engine.aggregate(col=col,
                               params=aggregator_params,
                               data_extractors=data_extractor,
                               public_partitions=public_partitions)
        budget_accountant.compute_budgets()

        # Simply assert pipeline can run for now.
        col = list(col)
        # TODO: Verify metrics related to public partitions are correct.

    def test_aggregate_error_metrics(self):
        # Arrange
        aggregator_params = pipeline_dp.AggregateParams(
            noise_kind=pipeline_dp.NoiseKind.GAUSSIAN,
            metrics=[pipeline_dp.Metrics.COUNT],
            max_partitions_contributed=1,
            max_contributions_per_partition=2)

        budget_accountant = pipeline_dp.NaiveBudgetAccountant(total_epsilon=2,
                                                              total_delta=1e-10)

        # Input collection has 10 privacy ids where each privacy id
        # contributes to the same 10 partitions, three times in each partition.
        col = []
        for i in range(10):
            for j in range(10):
                col.append((i, j))
                col.append((i, j))
                col.append((i, j))
        data_extractor = pipeline_dp.DataExtractors(
            privacy_id_extractor=lambda x: x[0],
            partition_extractor=lambda x: f"pk{x[1]}",
            value_extractor=lambda x: None)

        engine = dp_engine.UtilityAnalysisEngine(
            budget_accountant=budget_accountant,
            backend=pipeline_dp.LocalBackend())

        col = engine.aggregate(col=col,
                               params=aggregator_params,
                               data_extractors=data_extractor)
        budget_accountant.compute_budgets()

        col = list(col)

        # Assert
        # Assert a singleton is returned
        self.assertEqual(len(col), 1)
        # Assert there are 2 AggregateErrorMetrics, one for private partition
        # selection and 1 for count.
        self.assertEqual(len(col[0]), 2)
        # Assert count metrics are reasonable.
        self.assertAlmostEqual(col[0][1].abs_error_expected, -28, delta=1e-2)
        self.assertAlmostEqual(col[0][1].abs_error_variance, 146.47, delta=1e-2)
        self.assertAlmostEqual(col[0][1].rel_error_expected,
                               -0.933333,
                               delta=1e-5)
        self.assertAlmostEqual(col[0][1].rel_error_variance,
                               0.16275,
                               delta=1e-5)


if __name__ == '__main__':
    unittest.main()