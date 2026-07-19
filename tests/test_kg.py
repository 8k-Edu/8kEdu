import unittest

from agent.kg import _match_node, canonicalize_concept, concept_quality, observations_from_specs


class CanonicalizationTests(unittest.TestCase):
    def test_cross_teacher_attention_titles_collapse(self):
        first = canonicalize_concept("Self-Attention: Query-Key Interaction")
        second = canonicalize_concept("Self-Attention Mechanism in Transformers")
        self.assertEqual(first[0], "self-attention")
        self.assertEqual(first, second)

    def test_multi_head_stays_distinct_from_self_attention(self):
        name, _label = canonicalize_concept("Multi-head attention splits the input into four heads")
        self.assertEqual(name, "multi-head-attention")

    def test_structured_widget_scores_as_good_exemplar(self):
        quality = concept_quality({
            "title": "Softmax",
            "explanation": "Turns logits into probabilities.",
            "widget": "softmax",
            "params": {"logits": [1, 2, 3]},
        })
        self.assertGreaterEqual(quality, 0.7)


class MatchingTests(unittest.TestCase):
    def test_exact_canonical_name_is_perfect_match(self):
        node, score = _match_node("self-attention", [{"name": "self-attention"}])
        self.assertEqual(node["name"], "self-attention")
        self.assertEqual(score, 1.0)

    def test_unrelated_concept_is_not_forced_into_graph(self):
        node, _score = _match_node("mortgage-payment", [{"name": "self-attention"}])
        self.assertIsNone(node)


class SourceMetadataTests(unittest.TestCase):
    def test_cached_ai_video_keeps_real_teacher_identity(self):
        observations = observations_from_specs("4Bdc55j80l8", "ai_stem", [{
            "time": 120,
            "title": "Attention Mechanism in RNNs",
            "explanation": "Attention focuses on relevant words.",
            "widget": "attention",
            "params": {"q": [[1, 0]], "k": [[1, 0]]},
        }])

        self.assertEqual(observations[0]["channel"], "The AI Hacker")
        self.assertEqual(observations[0]["video_title"], "Illustrated Guide to Transformers Neural Network")


if __name__ == "__main__":
    unittest.main()
