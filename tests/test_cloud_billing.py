import unittest
from unittest.mock import patch

import serve


class FakeBillingDB:
    @staticmethod
    def user_billing(handle):
        return {"handle": handle, "credits": 20, "has_own_key": False}


class CloudKeyTests(unittest.TestCase):
    def setUp(self):
        serve._byok_keys.clear()

    def tearDown(self):
        serve._byok_keys.clear()

    def test_rejects_non_openrouter_key(self):
        with patch.object(serve, "_db", FakeBillingDB()), \
                patch.object(serve, "_authenticated_handle", return_value="auth-guest"):
            result = serve.set_openrouter_key(serve.KeyReq(key="not-a-key"), "Bearer test")

        self.assertFalse(result["ok"])
        self.assertNotIn("auth-guest", serve._byok_keys)

    def test_key_is_kept_in_memory_but_never_returned(self):
        key = "sk-or-v1-test-only"
        with patch.object(serve, "_db", FakeBillingDB()), \
                patch.object(serve, "_authenticated_handle", return_value="auth-guest"):
            result = serve.set_openrouter_key(serve.KeyReq(key=key), "Bearer test")

        self.assertTrue(result["ok"])
        self.assertTrue(result["has_own_key"])
        self.assertEqual(serve._byok_keys["auth-guest"], key)
        self.assertNotIn(key, repr(result))


class CreditReservationTests(unittest.TestCase):
    def test_credit_is_reserved_before_cloud_call(self):
        order = []

        class MeteredDB(FakeBillingDB):
            @staticmethod
            def spend_credit(_handle, _model, _n):
                order.append("spend")
                return 19

        class CloudBackend:
            @staticmethod
            def ask(*_args, **_kwargs):
                order.append("ask")
                return '{"has_concept":true,"widget":"softmax","title":"Softmax","explanation":"Normalize logits","params":{"logits":[1,2]}}'

        with patch.object(serve, "_db", MeteredDB()), \
                patch.object(serve, "_authenticated_handle", return_value="auth-guest"), \
                patch.object(serve, "_cloud_ctx", return_value=(CloudBackend(), True, "cloud-model")), \
                patch.object(serve, "nearest_frame", return_value={"file": "frame.jpg"}), \
                patch.object(serve, "_genre_for", return_value="general"), \
                patch.object(serve, "_cache_get_first", return_value=None), \
                patch.object(serve, "_cache_put"), \
                patch.object(serve, "_fire_event"):
            result = serve.make_widget(serve.Ask(text="logits", time=1, cloud=True), "Bearer test")

        self.assertEqual(order, ["spend", "ask"])
        self.assertEqual(result["credits"], 19)


if __name__ == "__main__":
    unittest.main()
