import html2pdf from "html2pdf.js";

export default function PdfExportButton({ targetId, fileName = "readiness-report.pdf" }) {
  async function handleExport() {
    const source = document.getElementById(targetId);
    if (!source) return;

    const clone = source.cloneNode(true);
    clone.removeAttribute("id");
    clone.classList.remove("pdf-print-root", "pdf-export-visible");
    clone.style.position = "static";
    clone.style.left = "auto";
    clone.style.top = "auto";
    clone.style.width = "1200px";
    clone.style.maxWidth = "1200px";
    clone.style.background = "#ffffff";
    clone.style.color = "#111827";
    clone.style.padding = "0";

    const wrapper = document.createElement("div");
    wrapper.style.position = "fixed";
    wrapper.style.left = "16px";
    wrapper.style.top = "16px";
    wrapper.style.zIndex = "999999";
    wrapper.style.background = "#ffffff";
    wrapper.style.padding = "0";
    wrapper.style.opacity = "1";
    wrapper.style.pointerEvents = "none";
    wrapper.appendChild(clone);
    document.body.appendChild(wrapper);

    await new Promise((r) => requestAnimationFrame(r));
    await new Promise((r) => setTimeout(r, 220));

    try {
      await html2pdf()
        .set({
          margin: [8, 8, 8, 8],
          filename: fileName,
          image: { type: "jpeg", quality: 0.98 },
          html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff" },
          jsPDF: { unit: "mm", format: "a4", orientation: "landscape" }
        })
        .from(wrapper)
        .save();
    } finally {
      wrapper.remove();
    }
  }

  return (
    <button className="btn btn-secondary" onClick={handleExport} type="button">
      Download PDF
    </button>
  );
}
