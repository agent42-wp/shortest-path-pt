# Shortest Path trên đồ thị đường bộ DIMACS bằng CSR

Repository này cài đặt các thuật toán tìm đường đi ngắn nhất trên dữ liệu DIMACS Challenge 9. Đồ thị được chuyển sang CSR (Compressed Sparse Row) bằng NumPy để giảm bộ nhớ và mở bằng memory-map.

Pipeline: `DIMACS .gr/.gr.gz -> preprocess_csr.py -> CSR -> Dijkstra / Bidirectional Dijkstra / Delta-stepping -> benchmark.py`.

Trọng số được giữ nguyên theo bộ DIMACS. `USA-road-d` thường là khoảng cách; `USA-road-t` thường là thời gian. Chương trình không tự đổi đơn vị.

## Cài đặt

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Chuyển DIMACS sang CSR

Chuyển mỗi dataset một lần. Lệnh đọc streaming, tạo CSR xuôi/ngược và lưu `.npy` cùng metadata `.json`:

```bash
python3 preprocess_csr.py data/USA-road-t.NY.gr.gz --output data/NY
```

Prefix `data/NY` tạo `NY.json`, `NY.row.npy`, `NY.col.npy`, `NY.weight.npy` và các file tương ứng có tiền tố `NY.reverse`. Có thể dùng trực tiếp `.gr.gz`; với USA cần vài phút và thêm dung lượng SSD.

## Chạy truy vấn

```bash
# Dijkstra, baseline tuần tự
python3 shortest_path.py --graph data/NY --algorithm dijkstra --source 1 --target 100000

# Bidirectional Dijkstra, phù hợp cho một cặp source-target
python3 shortest_path.py --graph data/NY --algorithm bidirectional --source 1 --target 100000

# Delta-stepping baseline bucket
python3 shortest_path.py --graph data/NY --algorithm delta --source 1 --target 100000 --delta 100

# In node của đường đi
python3 shortest_path.py --graph data/NY --algorithm dijkstra --source 1 --target 100000 --print-path

# In từng cung, trọng số và tổng để kiểm tra distance
python3 shortest_path.py --graph data/NY --algorithm dijkstra --source 1 --target 100000 --print-edges
```

Khi dùng `--print-edges`, `path_weight_sum` phải bằng `distance`.

## Benchmark

```bash
python3 benchmark.py --graph data/NY --source 1 --target 100000 --repeats 3 --output results-ny.csv
```

Giữ nguyên source/target khi so sánh và chạy từng dataset một để RAM ổn định.

## Các dataset

```bash
python3 preprocess_csr.py data/USA-road-t.NW.gr.gz --output data/NW
python3 shortest_path.py --graph data/NW --algorithm bidirectional --source 1 --target 1000000

python3 preprocess_csr.py data/USA-road-t.COL.gr.gz --output data/COL
python3 shortest_path.py --graph data/COL --algorithm bidirectional --source 1 --target 400000

python3 preprocess_csr.py data/USA-road-t.CTR.gr.gz --output data/CTR
python3 shortest_path.py --graph data/CTR --algorithm bidirectional --source 1 --target 1000000

python3 preprocess_csr.py data/USA-road-d.USA.gr.gz --output data/USA-d
python3 shortest_path.py --graph data/USA-d --algorithm bidirectional --source 1 --target 1234567
```

Thứ tự nên thử trên RAM 16 GB: `NY -> NW -> COL -> CTR -> USA`. Với CTR/USA, chạy Bidirectional trước rồi mới thử Delta-stepping.

## Vai trò các file

| File                  | Vai trò                                                                                            |
| --------------------- | -------------------------------------------------------------------------------------------------- |
| `csr_graph.py`        | Tạo CSR từ DIMACS và cung cấp lớp `CSRGraph` mở mảng bằng memory-map.                              |
| `preprocess_csr.py`   | Lệnh chuyển `.gr/.gr.gz` sang CSR.                                                                 |
| `shortest_path.py`    | Dijkstra, Bidirectional Dijkstra, Delta-stepping, dựng đường đi và `--print-path`/`--print-edges`. |
| `benchmark.py`        | Chạy lặp, lấy median thời gian và ghi CSV.                                                         |
| `decompress_graph.py` | Giải nén `.gr.gz` thành `.gr`; không bắt buộc cho CSR.                                             |
| `requirements.txt`    | Phụ thuộc Python, hiện gồm NumPy.                                                                  |

## Ý nghĩa đầu ra

`nodes` là số đỉnh; `arcs` là số cung; `distance` là tổng trọng số ngắn nhất; `path_nodes` là số node trong đường đi; `elapsed_seconds` là thời gian truy vấn, không gồm tiền xử lý; `path_weight_sum` là tổng khi dùng `--print-edges`.


#test bellman 
python3 distributed_bellman_ford.py   data/USA-road-t.NY.gr.gz   --source 1   --target 1000   --workers 2  