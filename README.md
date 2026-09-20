# Bellman-Ford phân tán trên mạng đường bộ DIMACS

## Tách yêu cầu và phạm vi triển khai

Tài liệu `YÊU CẦU BÀI TẬP CUỐI KỲ.pdf` yêu cầu: trình bày bài toán/nguyên lý/độ phức tạp/ưu nhược điểm; xây dựng chương trình có đầu vào và đầu ra; chạy trên dữ liệu lớn; đo thời gian ở nhiều quy mô; và phân tích khả năng mở rộng. Phần mã trong repository đáp ứng phần cài đặt và là nền tảng để ghi nhận thực nghiệm. Các con số thời gian phải được đo trên máy chạy báo cáo, không điền số giả định.

## Ý tưởng thuật toán

Đồ thị có hướng gồm đỉnh giao lộ và cung đường, trọng số là thời gian/chi phí. Ở mỗi superstep, mỗi worker xử lý các cung có đỉnh nguồn `u % P = worker_id`, đọc cùng một snapshot khoảng cách, rồi gửi đề xuất `(đỉnh đích, khoảng cách mới, đỉnh trước)` về coordinator. Coordinator lấy min theo đỉnh, cập nhật vector khoảng cách dùng chung và bắt đầu vòng tiếp theo. Khi không còn cập nhật, nghiệm đã hội tụ. Vì trọng số dương, đây cũng là mô hình định tuyến phù hợp; Bellman-Ford vẫn đúng cho trọng số âm và phát hiện chu trình âm có thể bổ sung bằng vòng thứ `|V|`.

Độ phức tạp tuần tự lý thuyết là `O(VE)`, bộ nhớ `O(V+E)`. Mặc định chương trình dùng frontier: mỗi superstep chỉ duyệt cung đi ra từ các node vừa được cải thiện, nên thường nhanh hơn quét toàn bộ cung. `--full-scan` giữ lại baseline để so sánh. Với `P` worker, chi phí thực tế còn phụ thuộc số superstep, phân vùng, CPU, RAM và truyền proposal.

## Chạy chương trình

```bash
python3 distributed_bellman_ford.py data/USA-road-t.NY.gr.gz --source 1 --target 100000 --workers 4
python3 distributed_bellman_ford.py data/USA-road-t.COL.gr.gz --source 1 --target 400000 --workers 8
python3 distributed_bellman_ford.py data/USA-road-t.NY.gr --source 1 --target 100000 --workers 4 --full-scan
```

Có thể giải nén một lần để giảm chi phí CPU giải gzip trong mỗi lần khởi tạo worker:

```bash
python3 decompress_graph.py data/USA-road-t.NY.gr.gz
python3 distributed_bellman_ford.py data/USA-road-t.NY.gr --source 1 --target 100000 --workers 4
```

Giải nén thường giúp giảm thời gian đọc khi chạy lặp nhiều lần, nhưng cần thêm dung lượng đĩa và không loại bỏ chi phí chính của thuật toán: tạo proposal, truyền dữ liệu và merge tuần tự sau mỗi superstep.

NY (264,346 đỉnh/733,846 cung) và COL (435,666/1,057,066) phù hợp cho chạy đầy đủ trên máy cá nhân. CTR (14,081,816/34,292,496) và USA (23,947,347/58,333,344) là mức lớn; cần RAM/SSD đủ và nên tăng `--workers`. Mỗi partition được đọc từ file nén khi cần và cache trong process worker; coordinator không nhân bản adjacency.

## Thiết kế thí nghiệm theo yêu cầu

Chạy cùng `source`, số worker và cách đo cho ba mức: NY (nhỏ), COL (trung bình), CTR hoặc USA (lớn). Ghi `nodes`, `arcs`, `workers`, `rounds`, `elapsed_seconds`, khoảng cách và số đỉnh đường đi vào bảng báo cáo. Lặp mỗi cấu hình ít nhất 3 lần và lấy median; chạy thêm `workers = 1, 2, 4, 8` để vẽ speedup. Cần nêu giới hạn: Bellman-Ford nhiều vòng đồng bộ, proposal có thể lớn, đọc gzip tốn CPU, và mô phỏng process trên một máy chưa phải triển khai cluster thật.

## Đầu vào/đầu ra

Đầu vào là file DIMACS `.gr`/`.gr.gz`, `--source`, tùy chọn `--target` và số worker. Đầu ra gồm kích thước đồ thị, số vòng, thời gian, khoảng cách ngắn nhất và đường đi node-by-node. Node không reachable được in là `unreachable`.

## Pipeline CSR thực tế cho máy cá nhân

Để chạy các bộ lớn mà không tạo list tuple Python cho hàng chục triệu cung, có thể chuyển graph sang CSR một lần. Bộ chuyển đổi đọc file theo hai lượt và tạo cả CSR xuôi/ngược dưới dạng NumPy memory-mapped arrays:

```bash
python3 preprocess_csr.py data/USA-road-t.NY.gr.gz --output data/NY
python3 shortest_path.py --graph data/NY --algorithm dijkstra --source 1 --target 100000
python3 shortest_path.py --graph data/NY --algorithm bidirectional --source 1 --target 100000
python3 shortest_path.py --graph data/NY --algorithm delta --source 1 --target 100000 --delta 100
```

`bidirectional` là lựa chọn chính cho truy vấn một cặp nguồn-đích. `delta` hiện là baseline tuần tự đúng để chọn kích thước bucket; phần MPI/Numba song song nên được benchmark riêng sau khi CSR và kết quả đã ổn định. Có thể thêm `--print-path` khi cần in toàn bộ đường đi. Mỗi dataset nên được tiền xử lý và chạy riêng để giữ RAM ổn định; Bellman-Ford cũ vẫn được giữ làm mã tham chiếu.


