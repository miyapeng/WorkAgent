"""文件格式层：只负责读写文件，不接触隐藏答案。"""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

FIELDS = ["region", "revenue", "revenue_change", "conversion", "conversion_change", "anomaly"]


def write_xlsx(path, headers, rows):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append([row[key] for key in headers])
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = 22
    book.save(path)


def read_xlsx(path):
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        values = list(book.active.values)
        return [dict(zip(values[0], row)) for row in values[1:]] if values else []
    finally:
        book.close()


def pdf_text(path):
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def font(size):
    # Pillow 自带字体；不依赖机器上是否安装中文字体。
    return ImageFont.load_default(size=size)


def dashboard(path, regions):
    image = Image.new("RGB", (1000, 560), "#f3f6fa")
    draw = ImageDraw.Draw(image)
    draw.text((40, 30), "Latest regional conversion", font=font(36), fill="#12223b")
    for i, row in enumerate(regions):
        y = 120 + i * 100
        draw.text((40, y), f"Region {row['region']}", font=font(28), fill="#12223b")
        draw.rectangle((240, y, 240 + int(row["conversion"] * 6000), y + 42), fill="#377bcb")
        draw.text((790, y), f"{row['conversion']:.1%}", font=font(30), fill="#12223b")
    image.save(path)  # 不嵌入文本元数据；当前转化率只出现在像素里。


def previous_report(path, regions):
    pdf = canvas.Canvas(str(path))
    pdf.setTitle("Previous quarter baseline")
    pdf.drawString(40, 790, "Previous quarter baseline (not current metrics)")
    for i, row in enumerate(regions):
        pdf.drawString(40, 740 - i * 35,
                       f"{row['region']} revenue={row['previous_revenue']:.2f} "
                       f"conversion={row['previous_conversion']:.4f}")
    pdf.save()


def report_line(row):
    return (f"{row['region']} | revenue={row['revenue']:.2f} | "
            f"change={row['revenue_change']:.4f} | conversion={row['conversion']:.4f} | "
            f"delta={row['conversion_change']:.4f} | anomaly={int(row['anomaly'])}")


def write_report(path, rows, narrative):
    """V0 采用公开的固定数值行格式，便于确定性验证；自由报告留待后续。"""
    import textwrap

    pdf = canvas.Canvas(str(path))
    pdf.setTitle("Quarterly sales brief")
    pdf.drawString(40, 790, "Quarterly sales brief")
    pdf.setFont("Helvetica", 9)
    for i, row in enumerate(rows):
        pdf.drawString(40, 745 - i * 28, report_line(row))
    pdf.setFont("Helvetica", 11)
    for i, line in enumerate(textwrap.wrap(narrative, 85)[:15]):
        pdf.drawString(40, 570 - i * 18, line)
    pdf.showPage()
    pdf.drawString(40, 790, "Regional revenue comparison")
    chart = Image.new("RGB", (900, 480), "white")
    draw = ImageDraw.Draw(chart)
    maximum = max(max(row["revenue"] for row in rows), 1)
    for i, row in enumerate(rows):
        y = 30 + i * 105
        draw.text((20, y), row["region"], font=font(28), fill="black")
        draw.rectangle((80, y, 80 + max(1, int(600 * row["revenue"] / maximum)), y + 50), fill="#377bcb")
        draw.text((700, y), str(row["revenue"]), font=font(24), fill="black")
    buffer = BytesIO()
    chart.save(buffer, format="PNG")
    buffer.seek(0)
    pdf.drawImage(ImageReader(buffer), 40, 380, width=510, height=272)
    pdf.save()
