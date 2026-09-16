from app.main import parse_vision_command


def test_parse_vision_command_preserves_quoted_windows_path_with_spaces() -> None:
    command = ':vision "C:\\Users\\chitz\\Pictures\\Screenshots\\Screenshot 2026-09-15 183941.png" what is this image'

    image_path, prompt = parse_vision_command(command)

    assert image_path == r'C:\Users\chitz\Pictures\Screenshots\Screenshot 2026-09-15 183941.png'
    assert prompt == 'what is this image'


def test_parse_vision_command_supports_unquoted_path_without_spaces() -> None:
    command = r':vision C:\test.png describe this image'

    image_path, prompt = parse_vision_command(command)

    assert image_path == r'C:\test.png'
    assert prompt == 'describe this image'


def test_parse_vision_command_uses_default_prompt_when_question_missing() -> None:
    command = r':vision C:\test.png'

    image_path, prompt = parse_vision_command(command)

    assert image_path == r'C:\test.png'
    assert prompt == 'Describe the image and mention only visually supported details.'


def test_parse_vision_command_rejects_empty_command() -> None:
    try:
        parse_vision_command(':vision')
    except ValueError as exc:
        assert str(exc) == 'Usage: :vision <image-path> <question>'
    else:
        raise AssertionError('Expected ValueError')
