import time
import unittest

import submission


SMALL_REASSIGNMENT = """task_id_list\tcourier_id\ttotal_score\twillingness
T1\tC1\t90.0\t0.90
T1\tC2\t10.0\t0.90
T2\tC1\t10.0\t0.90
T2\tC2\t90.0\t0.90
"""


class SubmissionTailSearchTest(unittest.TestCase):
    def test_courier_reassignment_can_improve_swapped_singles(self):
        instance = submission.parse_input(SMALL_REASSIGNMENT)
        selected = {
            ("T1",): ("T1", ["C1"]),
            ("T2",): ("T2", ["C2"]),
        }
        submission.REJECT_PENALTY = 100.0
        before = submission.evaluate(instance, selected)
        improved = submission.courier_reassignment_search(
            instance,
            selected,
            time.perf_counter() + 0.5,
            4,
        )
        after = submission.evaluate(instance, improved)
        self.assertTrue(after[0])
        self.assertTrue(submission.better(after, before))
        self.assertEqual(improved[("T1",)][1], ["C2"])
        self.assertEqual(improved[("T2",)][1], ["C1"])


if __name__ == "__main__":
    unittest.main()
