from po.numtok import find_numbers, values_match, is_trivial

def test_token_rules():
    vals = [n.value for n in find_numbers("ResNet-50 gets 87.3% (−0.5) on 1,024 samples, F1 0.91, 1e-4, 1.2M params")]
    assert vals == [87.3, -0.5, 1024.0, 0.91, 0.0001]
    n = find_numbers("87.30")[0]; assert (n.decimals, n.percent) == (2, False)
    assert find_numbers("87.3%")[0].percent and is_trivial(find_numbers("3")[0])

def test_values_match():
    assert values_match(87.3, 1, 87.31) and not values_match(87.3, 1, 87.36)

def _v(t):
    return [n.value for n in find_numbers(t)]

def test_sign_contexts():
    assert _v("a -5") == [-5.0]
    assert _v("12 +3") == [12.0, 3.0] and find_numbers("12 +3")[1].token == "+3"
    assert _v("=+4") == [4.0] and find_numbers("=+4")[0].token == "+4"
    assert _v("x-5") == []

def test_forms():
    assert _v(".5") == [0.5]
    assert _v("1234") == [1234.0]
    assert _v("1,024") == [1024.0]

def test_name_prefixes_and_suffixes():
    assert _v("ResNet-50") == [] and _v("v2.1") == [] and _v("Fig.3") == []
    assert _v("5%x") == []
