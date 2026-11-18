# Báo cáo Day 09 — Do Anh Hoang, 2a202604061

## 1. Kết luận trước

Với cấu hình đã chọn, pipeline nhận **193/224 ảnh** và loại **31 ảnh** ở bước intake. Sau autofix và mô phỏng duyệt 80 ảnh, QC cuối còn **0 lỗi bắt buộc** và cảnh báo trên **13/193 ảnh (6.74%)**. Gate kết luận **Release** vì tỉ lệ dưới ngưỡng 10%; dataset được xuất tại `submission/export/clean_v1/`.

## 2. Lỗi và phân việc

Số liệu lấy từ `02_error_list_v1`; “ảnh/dòng” là số ảnh khác nhau / số issue. Lỗi intake được máy loại khỏi dataset; autofix xử lý lỗi có cách sửa an toàn; cảnh báo và nhãn thiếu cần người xem.

| Mã lỗi | Ảnh/dòng | Ai xử lý | Vì sao |
|---|---:|---|---|
| BAD_CLASS_ID | 6/6 | Máy | Xóa dòng có class ID ngoài danh sách. |
| BAD_CLASS_NAME | 1/2 | Máy | Ghi lại names theo cấu hình lớp. |
| BAD_FORMAT | 3/3 | Máy | Xóa dòng không parse được. |
| BAD_SIZE | 3/3 | Máy | Loại ảnh nhỏ hơn kích thước tối thiểu. |
| BOX_HUGE | 3/3 | Người | Cảnh báo box phủ diện tích lớn; cần xem nội dung ảnh. |
| BOX_OUT_OF_IMAGE | 8/8 | Máy | Clip box vào biên ảnh hoặc xóa nếu không còn diện tích. |
| BOX_TINY | 4/6 | Người | Cạnh ngắn dưới ngưỡng pixel; người quyết định vật thể có đáng gán nhãn. |
| BOX_ZERO | 4/4 | Máy | Xóa box có chiều rộng/chiều cao không dương. |
| CLASS_RARE | 1/4 | Người | Lớp ít mẫu; cần xem xét cân bằng dữ liệu. |
| CORRUPT_IMAGE | 2/2 | Máy | Loại ảnh không mở được. |
| DUP_BOX | 7/7 | Máy | Xóa dòng box trùng cùng lớp. |
| DUP_IMAGE_EXACT | 8/8 | Máy | Loại ảnh trùng từng byte. |
| DUP_IMAGE_NEAR | 7/7 | Máy | Loại ảnh trùng gần đúng theo pHash. |
| EMPTY_LABEL | 11/11 | Người | Xác nhận ảnh nền hay nhãn bị bỏ sót. |
| LEAK_TEST | 11/11 | Máy | Loại ảnh trùng với tập test/validation. |
| MISSING_LABEL_FILE | 6/6 | Người | Máy không thể tự bịa nhãn; cần người gán. |
| POSSIBLE_FALSE_POS | 26/28 | Người | Box nhãn không khớp dự đoán; model chỉ đưa cảnh báo. |
| POSSIBLE_LOOSE_BOX | 11/11 | Người | Xem lại box có thể lỏng/lệch. |
| POSSIBLE_MISSING | 32/32 | Người | Model thấy vật thể có thể chưa được gán nhãn. |
| POSSIBLE_WRONG_CLASS | 13/13 | Người | Xác nhận lớp đối tượng. |

Hàng đợi xếp giảm dần theo tổng trọng số cảnh báo và fix, có xét confidence; ảnh thiếu nhãn được ưu tiên cao (`NEEDS_LABEL = 10`). Ảnh đầu hàng `img_0020` có cả FIXED_DROP_LINE, POSSIBLE_MISSING và POSSIBLE_WRONG_CLASS nên được ưu tiên. Trong 80 ảnh duyệt, **67 ảnh có ít nhất một cờ ngữ nghĩa**, tổng cộng **76 cờ**: POSSIBLE_MISSING 32, POSSIBLE_WRONG_CLASS 13, POSSIBLE_LOOSE_BOX 11, POSSIBLE_FALSE_POS 20. Một ảnh có thể có nhiều cờ.

## 3. Calibration

Sweep trên tập hiệu chuẩn gợi ý `duplicates.phash_dist = 16` và `second_opinion.conf = 0.8`; hai giá trị này đã được đặt trong `configs/pipeline.yaml`.

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do / đánh đổi |
|---|---:|---:|---|---|
| `duplicates.phash_dist` | 2 | 16 | DUP_IMAGE_NEAR: 1.00/0.50 → 1.00/0.83; DUP_IMAGE_EXACT: 1.00/1.00 → 1.00/1.00 | Near-duplicate F1 tăng 0.67 → 0.91. Ở 20, exact-duplicate recall giảm còn 0.33. |
| `second_opinion.conf` | 0.25 | 0.8 | WRONG_CLASS: 0.56/0.83 → 1.00/0.83 | MISSING: precision/recall 0.50/1.00 → 0.67/0.75; LOOSE_BOX recall giảm 0.40 → 0.20. FALSE_POS không đổi (0.31/1.00). |

Điểm có thể gây hiểu nhầm: chỉ có **6** ca DUP_IMAGE_NEAR được chèn trong calibration; ngưỡng 16 vẫn bỏ sót 1 ca (recall 0.83). Trên raw, ngưỡng này loại **31/224 ảnh**, so với 19/224 ở ngưỡng 2; vì vậy phần tăng loại ảnh cần được kiểm tra trực quan để phân biệt ảnh gần trùng thật với ảnh hợp lệ. Tương tự, conf 0.8 tăng precision WRONG_CLASS nhưng giảm recall MISSING/LOOSE_BOX.

## 4. Cửa chặn và điểm mù

Đã chạy `python -X utf8 -m pipeline.run --budget 0 --work work/run_nb --reports work/rep_nb --export-dir work/exp_nb` với cấu hình hiện tại. Không có lượt duyệt, QC cuối còn **6 lỗi bắt buộc**; gate kết luận **Rework**, mã thoát **20**, và `work/exp_nb/clean_v1/manifest.json` **không tồn tại**. Đây là bằng chứng lỗi bắt buộc chặn xuất. Ở lượt duyệt ngân sách 80, lỗi được xử lý và pipeline kết thúc Release như mục 1.

Hai điểm mù có bằng chứng từ calibration:

1. Ý kiến thứ hai dễ báo nhầm: POSSIBLE_FALSE_POS có precision **0.31** (5 TP, 11 FP); POSSIBLE_LOOSE_BOX precision **0.50**, recall **0.20** ở conf 0.8. Đây là cảnh báo cho người xem, không phải kết luận nhãn sai.
2. So trùng gần đúng vẫn bỏ sót ảnh: tại ngưỡng 16, DUP_IMAGE_NEAR recall **0.83** (5/6); tăng tới 20 làm DUP_IMAGE_EXACT recall giảm còn **0.33**. Một ngưỡng pHash không bắt được mọi kiểu biến đổi mà không tạo đánh đổi.

## 5. Train: raw vs clean

Chưa chạy train/so sánh raw-clean; `submission/results/` chưa có kết quả. Vì vậy chưa có mAP50 hoặc độ lệch chuẩn giữa các seed để kết luận ảnh hưởng của QC đến chất lượng mô hình.

## 6. Quyết định và ghi chú AI

Quyết định hiện tại là **Release**: không còn lỗi bắt buộc và 13/193 ảnh còn cảnh báo, dưới ngưỡng 10%. Cần tiếp tục xem xét các cảnh báo ngữ nghĩa và kiểm tra trực quan ảnh bị loại ở ngưỡng pHash 16; nếu các cảnh báo chưa được xử lý tăng lên ít nhất 20/193 ảnh, gate sẽ chuyển sang Hold.

- **Prompt chính:** “Viết lần lượt `label_format.py`, `gate.py`, `autofix.py`, `second_opinion.py`; mục tiêu 79 tests pass.”
- **Kiểm chứng:** chạy toàn bộ pytest (**79 passed**), pipeline end-to-end, calibration hai sweep và lượt gate ngân sách 0.
- **Một lần AI sai:** lần chạy gate thử đầu tiên dùng terminal mã hóa cp1252 nên lỗi UnicodeEncodeError trước khi pipeline bắt đầu; đã chạy lại với `-X utf8`, thu được kết quả Rework như trên.
