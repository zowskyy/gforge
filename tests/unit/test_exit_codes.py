from godotforge_core.exit_codes import EXIT_CODE_MESSAGES, ForgeExitCode


def test_codes_distinct() -> None:
    values = [int(code) for code in ForgeExitCode]
    assert len(values) == len(set(values))
    assert 0 in values


def test_messages_cover_all() -> None:
    assert set(EXIT_CODE_MESSAGES) == set(ForgeExitCode)
