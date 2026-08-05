"""utils.file_utils 单元测试（无 GUI）。"""
import os

from utils.file_utils import (
    copy_image_with_seq_name,
    next_seq_number,
    validate_windows_path_name,
)


def test_validate_valid_names():
    assert validate_windows_path_name("普通名字") == (True, "")
    assert validate_windows_path_name("Comic 001") == (True, "")


def test_validate_empty():
    assert validate_windows_path_name("")[0] is False
    assert validate_windows_path_name("   ")[0] is False


def test_validate_illegal_chars():
    for bad in ("a/b", "a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b"):
        assert validate_windows_path_name(bad)[0] is False


def test_validate_reserved_names():
    for reserved in ("CON", "con.txt", "PRN", "AUX", "NUL",
                     "COM0", "COM1", "COM9", "LPT0", "LPT1", "LPT9"):
        assert validate_windows_path_name(reserved)[0] is False


def test_validate_too_long():
    assert validate_windows_path_name("x" * 201)[0] is False
    assert validate_windows_path_name("x" * 200)[0] is True


def test_validate_trailing_dot_or_space():
    assert validate_windows_path_name("name.")[0] is False
    assert validate_windows_path_name("name ")[0] is False
    assert validate_windows_path_name(".hidden")[0] is False


def test_next_seq_number(tmp_path):
    assert next_seq_number(str(tmp_path)) == 1
    (tmp_path / "000001.jpg").touch()
    (tmp_path / "000003.png").touch()
    (tmp_path / "ignore.txt").touch()
    assert next_seq_number(str(tmp_path)) == 4


def test_copy_image_with_seq_name(tmp_path, make_images):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    paths = make_images(str(src_dir), 1)
    dest_dir = tmp_path / "dest"

    filename, dest, used_seq = copy_image_with_seq_name(paths[0], str(dest_dir), 1)
    assert filename == "0000001.png"
    assert used_seq == 1
    assert os.path.isfile(dest)

    # 序号冲突时自动递增，并返回实际使用的序号
    filename2, dest2, used_seq2 = copy_image_with_seq_name(paths[0], str(dest_dir), 1)
    assert filename2 == "0000002.png"
    assert used_seq2 == 2
    assert os.path.isfile(dest2)
