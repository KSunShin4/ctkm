def test_opencv_barcode_detector_is_available_in_runtime():
    import cv2

    assert hasattr(cv2, "barcode_BarcodeDetector")
    detector = cv2.barcode_BarcodeDetector()
    assert hasattr(detector, "detectAndDecodeWithType")
