from pedalfleet import rules

BLOCK = (
    "# --- pedalfx fleet rules v1 begin (managed) ---\n"
    "(rule \"fleet: a\" (constraint clearance (min 0.1mm)))\n"
    "# --- pedalfx fleet rules v1 end ---\n"
)
BLOCK2 = BLOCK.replace("0.1mm", "0.2mm")


def test_create_from_nothing():
    text, status = rules.splice(None, BLOCK)
    assert status == rules.CREATED
    assert text == "(version 1)\n" + BLOCK


def test_create_from_blank_file():
    text, status = rules.splice("   \n", BLOCK)
    assert status == rules.CREATED
    assert text.startswith("(version 1)\n")


def test_insert_after_version_line_keeps_local_rules():
    local = "(version 1)\n(rule \"mine\" (constraint clearance (min 0.3mm)))\n"
    text, status = rules.splice(local, BLOCK)
    assert status == rules.INSERTED
    assert text == "(version 1)\n" + BLOCK + "(rule \"mine\" (constraint clearance (min 0.3mm)))\n"


def test_insert_when_version_line_has_no_trailing_newline():
    text, status = rules.splice("(version 1)", BLOCK)
    assert status == rules.INSERTED
    assert text == "(version 1)\n" + BLOCK


def test_replace_existing_block_in_place():
    local = "(version 1)\n" + BLOCK + "(rule \"mine\" (constraint clearance (min 0.3mm)))\n"
    text, status = rules.splice(local, BLOCK2)
    assert status == rules.REPLACED
    assert text == "(version 1)\n" + BLOCK2 + "(rule \"mine\" (constraint clearance (min 0.3mm)))\n"


def test_replace_matches_any_block_version():
    old = BLOCK.replace("v1", "v7")
    text, status = rules.splice("(version 1)\n" + old, BLOCK)
    assert status == rules.REPLACED
    assert "v7" not in text


def test_unchanged_when_block_identical():
    text, status = rules.splice("(version 1)\n" + BLOCK, BLOCK)
    assert status == rules.UNCHANGED


def test_malformed_without_version_line():
    text, status = rules.splice("(rule \"x\" (constraint clearance (min 1mm)))\n", BLOCK)
    assert status == rules.MALFORMED


def test_malformed_with_two_version_lines():
    text, status = rules.splice("(version 1)\n\n(version 1)\n", BLOCK)
    assert status == rules.MALFORMED


def test_malformed_with_half_a_block():
    half = "(version 1)\n# --- pedalfx fleet rules v1 begin ---\n(rule \"a\")\n"
    text, status = rules.splice(half, BLOCK)
    assert status == rules.MALFORMED
    assert text == half


def test_find_block_and_version():
    text = "(version 1)\n" + BLOCK + "tail\n"
    start, end = rules.find_block(text)
    assert text[start:end] == BLOCK
    assert rules.block_version(text) == 1
    assert rules.find_block("(version 1)\n") is None
