"""Check an installed tecv2 wheel: scope, coexistence with the official cv2, and the calls Texture Extractor makes.

Run with the built wheel and the official opencv-python-headless 4.11.0.86 wheel both installed.
Pass --private-first to import tecv2 before cv2.
"""

import json
import platform
import sys

if "--private-first" in sys.argv:
    import tecv2 as cv
    import cv2 as shared_cv2
else:
    import cv2 as shared_cv2
    original_dnn = shared_cv2.dnn
    import tecv2 as cv
    assert shared_cv2.dnn is original_dnn
import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

assert sys.modules["cv2"] is shared_cv2 and sys.modules["tecv2"] is cv
assert shared_cv2 is not cv and shared_cv2.dnn is not cv.dnn
assert sys.modules["tecv2.dnn"] is cv.dnn and sys.modules["cv2.dnn"] is shared_cv2.dnn
assert hasattr(shared_cv2, "VideoCapture") and not hasattr(cv, "VideoCapture"), "videoio must not be built"
assert not hasattr(cv, "imread") and not hasattr(cv, "imshow"), "imgcodecs and highgui must not be built"
assert cv.__version__ == "4.11.0", cv.__version__
build = cv.getBuildInformation()
assert "FFMPEG:" not in build or "FFMPEG:                      NO" in build, build

rgb = np.zeros((64, 64, 3), np.float32)
rgb[16:48, 16:48] = (0.2, 0.4, 0.6)
inside = cv.inRange(rgb, (0.19, 0.39, 0.59), (0.21, 0.41, 0.61))
assert int((inside != 0).sum()) == 32 * 32

fill = rgb.copy()
flood_mask = np.zeros((66, 66), np.uint8)
cv.floodFill(fill, flood_mask, (20, 20), 0, (0.01,) * 3, (0.01,) * 3,
             4 | cv.FLOODFILL_MASK_ONLY | cv.FLOODFILL_FIXED_RANGE | (255 << 8))
assert int((flood_mask[1:-1, 1:-1] != 0).sum()) == 32 * 32

binary = (inside != 0).astype(np.uint8)
distance = cv.distanceTransform(binary, cv.DIST_L2, cv.DIST_MASK_PRECISE)
assert distance[32, 32] == 16 and distance[0, 0] == 0

small = cv.resize(rgb, (32, 32), interpolation=cv.INTER_AREA)
assert small.shape == (32, 32, 3) and np.allclose(small[16, 16], (0.2, 0.4, 0.6))
box = cv.boxFilter(binary.astype(np.float32), -1, (5, 5))
assert box[32, 32] == 1 and box[0, 0] == 0
shift = np.float32([[1, 0, 2], [0, 1, 3]])
moved = cv.warpAffine(binary.astype(np.float32), shift, (64, 64), flags=cv.INTER_LINEAR, borderMode=cv.BORDER_REPLICATE)
assert moved[19, 18] == 1 and moved[18, 17] == 0

weight = np.arange(1, 9, dtype=np.float32).reshape(2, 4, 1, 1) / 10
graph = helper.make_graph(
    [helper.make_node("Conv", ["image", "weight"], ["conv"], kernel_shape=[1, 1]), helper.make_node("Sigmoid", ["conv"], ["out"])],
    "tecv2_smoke",
    [helper.make_tensor_value_info("image", TensorProto.FLOAT, [1, 4, 8, 8])],
    [helper.make_tensor_value_info("out", TensorProto.FLOAT, [1, 2, 8, 8])],
    [numpy_helper.from_array(weight, "weight")],
)
model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 11)])
model.ir_version = 7
onnx.checker.check_model(model)
net = cv.dnn.readNetFromONNX(np.frombuffer(model.SerializeToString(), dtype=np.uint8))
image = np.random.default_rng(0).random((1, 4, 8, 8), dtype=np.float32)
net.setInput(image, "image")
result = net.forward("out")
expected = 1 / (1 + np.exp(-np.einsum("oi,bihw->bohw", weight[:, :, 0, 0], image)))
assert np.allclose(result, expected, atol=1e-5)

print(json.dumps(dict(platform=platform.platform(), machine=platform.machine(), python=sys.version,
                      numpy=np.__version__, opencv=cv.__version__, coexistence="PASS",
                      private_first="--private-first" in sys.argv, result="PASS"), indent=2))
print(build)
