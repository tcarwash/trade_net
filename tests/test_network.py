import unittest

from tradenet.network import Network


class NetworkTests(unittest.TestCase):
    def test_success_discovers_peer_and_reported_neighbors(self):
        net = Network("AG7SU")
        result = net.simulate("K7OR", 1024, loss=0, neighbors=[
            {"peer": "W7ABC", "goodput_bps": 37}])
        self.assertTrue(result["delivered"])
        self.assertEqual(net.peers["K7OR"]["kind"], "direct")
        self.assertEqual(net.peers["W7ABC"]["kind"], "reported")
        self.assertEqual(net.links["K7OR->W7ABC"]["kind"], "reported")
        self.assertGreater(net.links["AG7SU->K7OR"]["goodput_bps"], 0)

    def test_failure_does_not_discover_or_count_bytes(self):
        net = Network("AG7SU")
        result = net.simulate("K7OR", 1024, loss=1)
        self.assertFalse(result["delivered"])
        self.assertNotIn("K7OR", net.peers)
        self.assertEqual(net.links["AG7SU->K7OR"]["goodput_bps"], 0)
        self.assertGreater(result["missing_frames"], 0)

    def test_retries_are_attrition_not_extra_payload(self):
        a = Network("AG7SU")
        result = a.simulate("K7OR", 192, loss=.7)
        self.assertGreaterEqual(result["bytes_on_air_estimate"], result["unique_bytes"])
        self.assertEqual(result["frames"] - result["lost_frames"] <= 12, True)
        self.assertEqual(Network.from_dict(a.to_dict()).to_dict(), a.to_dict())

    def test_reported_cannot_downgrade_measured(self):
        net = Network("AG7SU")
        net.simulate("K7OR", 200, loss=0)
        net.simulate("W7ABC", 200, loss=0)
        net.discover("K7OR", [{"peer": "W7ABC", "goodput_bps": 5}])
        self.assertEqual(net.links["AG7SU->W7ABC"]["kind"], "observed")

    def test_digest_bounds(self):
        net = Network()
        net.discover("K7OR", [{"peer": f"P{i}", "goodput_bps": 50} for i in range(20)])
        self.assertEqual(len(net.peers), 10)

    def test_invalid_channel(self):
        with self.assertRaises(ValueError):
            Network().simulate("K7OR", 100, loss=1.2)


if __name__ == "__main__":
    unittest.main()
