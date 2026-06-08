#!/usr/bin/env node
/**
 * generate_cv_docx.js — ATS-safe CV document generator.
 * Usage: node generate_cv_docx.js <spec.json> <output.docx>
 *
 * ATS-safe: no tables, no Word headers/footers with floating content,
 * no images. All layout via paragraph/run styles.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  AlignmentType,
  BorderStyle,
  PageNumber,
  NumberFormat,
  Footer,
  Header,
  LevelFormat,
  convertInchesToTwip,
  HeadingLevel,
  TabStopType,
  TabStopPosition,
  WidthType,
  ShadingType,
} = require("docx");

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const A4_WIDTH_DXA = 11906;  // twips
const MARGIN_DXA = 1080;     // ~0.75 inch
const FONT = "Calibri";
const HEADING_COLOR = "1F4E79";
const BLACK = "000000";
const DARK_GRAY = "333333";

// ---------------------------------------------------------------------------
// Helper builders
// ---------------------------------------------------------------------------

function hr() {
  return new Paragraph({
    border: { bottom: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE, size: 6 } },
    spacing: { before: 80, after: 80 },
  });
}

function sectionHeading(text) {
  return new Paragraph({
    children: [
      new TextRun({
        text: text.toUpperCase(),
        bold: true,
        color: HEADING_COLOR,
        size: 22,
        font: FONT,
      }),
    ],
    spacing: { before: 160, after: 60 },
    border: { bottom: { color: HEADING_COLOR, space: 1, style: BorderStyle.SINGLE, size: 4 } },
  });
}

function bodyText(text, opts = {}) {
  return new Paragraph({
    children: [
      new TextRun({
        text,
        size: 20,
        font: FONT,
        color: opts.color || DARK_GRAY,
        bold: opts.bold || false,
        italics: opts.italic || false,
      }),
    ],
    spacing: { line: 276, before: opts.spaceBefore || 0, after: opts.spaceAfter || 40 },
    alignment: opts.align || AlignmentType.LEFT,
  });
}

function bulletPoint(text) {
  return new Paragraph({
    children: [
      new TextRun({ text, size: 20, font: FONT, color: DARK_GRAY }),
    ],
    bullet: { level: 0 },
    spacing: { line: 276, before: 20, after: 20 },
  });
}

function experienceHeader(role, company, period) {
  return new Paragraph({
    children: [
      new TextRun({ text: role, bold: true, size: 20, font: FONT, color: BLACK }),
      new TextRun({ text: "\t", size: 20, font: FONT }),
      new TextRun({ text: period, size: 18, font: FONT, color: "666666" }),
      new TextRun({ text: "\n", size: 20, font: FONT }),
      new TextRun({ text: company, italics: true, size: 19, font: FONT, color: "444444" }),
    ],
    tabStops: [
      { type: TabStopType.RIGHT, position: A4_WIDTH_DXA - MARGIN_DXA * 2 - 200 },
    ],
    spacing: { before: 120, after: 40 },
  });
}

// ---------------------------------------------------------------------------
// Main builder
// ---------------------------------------------------------------------------

function buildCV(spec) {
  const { personal, summary, skills, experience, certifications, role_applied_for } = spec;

  const children = [];

  // --- Name ---
  children.push(
    new Paragraph({
      children: [
        new TextRun({
          text: personal.full_name || "Candidate Name",
          bold: true,
          size: 36,
          font: FONT,
          color: HEADING_COLOR,
        }),
      ],
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 60 },
    })
  );

  // --- Contact line ---
  const contactParts = [
    personal.email,
    personal.phone,
    personal.location,
    personal.linkedin,
    personal.portfolio,
    personal.visa_status,
  ].filter(Boolean);

  children.push(
    new Paragraph({
      children: [
        new TextRun({
          text: contactParts.join("  |  "),
          size: 18,
          font: FONT,
          color: "555555",
        }),
      ],
      alignment: AlignmentType.CENTER,
      spacing: { after: 60 },
    })
  );

  children.push(hr());

  // --- Professional Summary ---
  if (summary) {
    children.push(sectionHeading("Professional Summary"));
    children.push(bodyText(summary, { spaceAfter: 80 }));
  }

  // --- Skills ---
  if (skills && skills.length > 0) {
    children.push(sectionHeading("Core Skills"));
    for (const skillGroup of skills) {
      const groupName = skillGroup.display_name || skillGroup.category || skillGroup.name || "";
      const items = (skillGroup.items || []).join("  ·  ");
      if (items) {
        children.push(
          new Paragraph({
            children: [
              ...(groupName ? [new TextRun({ text: groupName + ":  ", bold: true, size: 19, font: FONT, color: HEADING_COLOR })] : []),
              new TextRun({ text: items, size: 19, font: FONT, color: DARK_GRAY }),
            ],
            spacing: { line: 276, before: 30, after: 30 },
          })
        );
      }
    }
  }

  // --- Experience ---
  if (experience && experience.length > 0) {
    children.push(sectionHeading("Professional Experience"));
    for (const exp of experience) {
      children.push(experienceHeader(exp.role, exp.company, exp.period));
      for (const ach of (exp.achievements || [])) {
        children.push(bulletPoint(ach));
      }
    }
  }

  // --- Certifications ---
  if (certifications && certifications.length > 0) {
    children.push(sectionHeading("Certifications"));
    for (const cert of certifications) {
      const certText = typeof cert === "string" ? cert : (cert.name || JSON.stringify(cert));
      children.push(bulletPoint(certText));
    }
  }

  // --- Footer with page numbers ---
  const footer = new Footer({
    children: [
      new Paragraph({
        children: [
          new TextRun({ text: `${personal.full_name || ""} — CV    `, size: 16, font: FONT, color: "999999" }),
          new TextRun({ children: [PageNumber.CURRENT], size: 16, font: FONT, color: "999999" }),
          new TextRun({ text: " of ", size: 16, font: FONT, color: "999999" }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, font: FONT, color: "999999" }),
        ],
        alignment: AlignmentType.CENTER,
      }),
    ],
  });

  return new Document({
    sections: [
      {
        properties: {
          page: {
            margin: {
              top: MARGIN_DXA,
              right: MARGIN_DXA,
              bottom: MARGIN_DXA,
              left: MARGIN_DXA,
            },
          },
        },
        footers: { default: footer },
        children,
      },
    ],
    numbering: {
      config: [
        {
          reference: "default-bullet",
          levels: [
            {
              level: 0,
              format: LevelFormat.BULLET,
              text: "\u2022",
              alignment: AlignmentType.LEFT,
              style: {
                paragraph: { indent: { left: convertInchesToTwip(0.25), hanging: convertInchesToTwip(0.25) } },
                run: { font: "Symbol" },
              },
            },
          ],
        },
      ],
    },
  });
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

async function main() {
  const [,, specPath, outPath] = process.argv;
  if (!specPath || !outPath) {
    console.error("Usage: node generate_cv_docx.js <spec.json> <output.docx>");
    process.exit(1);
  }

  const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
  const doc = buildCV(spec);
  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outPath, buffer);
  console.log(`CV written to ${outPath} (${buffer.length} bytes)`);
}

main().catch((err) => {
  console.error("Error:", err.message);
  process.exit(1);
});
