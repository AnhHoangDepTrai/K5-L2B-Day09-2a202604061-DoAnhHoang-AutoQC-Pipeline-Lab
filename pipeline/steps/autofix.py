"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    image_codes = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
    fixes = []
    line_issues = defaultdict(dict)
    remove_stems = set()
    needs_label = set()
    rename_requested = False

    for issue in issues:
        if issue.severity != ERROR:
            continue
        if issue.code in drop_codes and issue.line is not None:
            line_issues[issue.image].setdefault(issue.line, set()).add(issue.code)
        elif issue.code == "BOX_OUT_OF_IMAGE" and issue.line is not None:
            line_issues[issue.image].setdefault(issue.line, set()).add(issue.code)
        elif issue.code.startswith("DUP_IMAGE_") or issue.code in image_codes:
            remove_stems.add(issue.image)
        elif issue.code == "MISSING_LABEL_FILE":
            needs_label.add(issue.image)
        elif issue.code == "BAD_CLASS_NAME":
            rename_requested = True

    for stem in sorted(remove_stems):
        image_path = ds.image_path(stem)
        label_path = ds.label_path(stem)
        if image_path is None and not label_path.exists():
            continue
        if image_path is not None:
            image_path.unlink()
        if label_path.exists():
            label_path.unlink()
        fixes.append({
            "image": stem, "line": "", "action": "remove_image",
            "before": "ảnh và nhãn", "after": "đã xoá khỏi dataset",
        })

    for stem in sorted(needs_label):
        if stem in remove_stems:
            continue
        fixes.append({
            "image": stem, "line": "", "action": "needs_label",
            "before": "(không có file)", "after": "chuyển người gán",
        })

    for stem, by_line in line_issues.items():
        if stem in remove_stems:
            continue
        path = ds.label_path(stem)
        if not path.exists():
            continue
        original_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        updated_lines = list(original_lines)
        for line_number in sorted(by_line):
            index = line_number - 1
            if index < 0 or index >= len(original_lines):
                continue
            codes = by_line[line_number]
            before = original_lines[index]
            if codes.intersection(drop_codes):
                updated_lines[index] = None
                fixes.append({
                    "image": stem, "line": line_number, "action": "drop_line",
                    "before": before, "after": "",
                })
                continue
            if "BOX_OUT_OF_IMAGE" not in codes:
                continue
            try:
                class_id, cx, cy, box_width, box_height = parse_yolo_line(before)
            except ValueError:
                continue

            left = max(0.0, cx - box_width / 2)
            top = max(0.0, cy - box_height / 2)
            right = min(1.0, cx + box_width / 2)
            bottom = min(1.0, cy + box_height / 2)
            if right <= left or bottom <= top:
                updated_lines[index] = None
                fixes.append({
                    "image": stem, "line": line_number, "action": "drop_line",
                    "before": before, "after": "",
                })
            else:
                clipped = (
                    class_id, (left + right) / 2, (top + bottom) / 2,
                    right - left, bottom - top,
                )
                after = " ".join(
                    [str(clipped[0])] + [f"{value:.10g}" for value in clipped[1:]]
                )
                updated_lines[index] = after
                fixes.append({
                    "image": stem, "line": line_number, "action": "clip_box",
                    "before": before, "after": after,
                })
        if updated_lines != original_lines:
            retained_lines = [line for line in updated_lines if line is not None]
            path.write_text(
                "\n".join(retained_lines) + ("\n" if retained_lines else ""),
                encoding="utf-8",
            )

    if rename_requested and ds.yaml_path.exists():
        data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        expected = {i: name for i, name in enumerate(cfg["classes"])}
        current = data.get("names") or {}
        normalized = (
            {i: name for i, name in enumerate(current)}
            if isinstance(current, list)
            else {int(key): name for key, name in current.items()}
        )
        if normalized != expected:
            before = str(current)
            data["names"] = expected
            ds.yaml_path.write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            fixes.append({
                "image": "data.yaml", "line": "", "action": "rename_classes",
                "before": before, "after": str(expected),
            })

    return fixes
