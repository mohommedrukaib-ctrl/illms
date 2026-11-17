"""
QR Code Generator Utility for ILIMS
Generates pure vector SVG QR codes inline without requiring file storage or external CDNs.
"""
import io
import qrcode
import qrcode.image.svg


def generate_qr_svg(data_string, box_size=5):
    """
    Generate an inline SVG string for a given text string or tracking code.
    Returns safe vector SVG markup ready for embedding into HTML.
    """
    if not data_string:
        data_string = "ILIMS-UNKNOWN"

    factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=1,
        image_factory=factory,
    )
    qr.add_data(data_string)
    qr.make(fit=True)

    img = qr.make_image()
    stream = io.BytesIO()
    img.save(stream)
    return stream.getvalue().decode("utf-8")