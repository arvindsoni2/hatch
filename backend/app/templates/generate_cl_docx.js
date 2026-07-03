#!/usr/bin/env node
/**
 * generate_cl_docx.js — ATS-safe Cover Letter generator.
 * Usage: node generate_cl_docx.js <spec.json> <output.docx>
 */

"use strict";

const fs = require("fs");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  AlignmentType,
  BorderStyle,
  PageNumber,
  Footer,
  LevelFormat,
  convertInchesToTwip,
} = require("docx");

let FONT = "Aptos";
let HEADING_COLOR = "1F4E79";
const DARK_GRAY = "333333";
let MARGIN_DXA = 1080;

function hr() {
  return new Paragraph({
    border: { bottom: { color: "CCCCCC", space: 1, style: BorderStyle.SINGLE, size: 4 } },
    spacing: { before: 60, after: 60 },
  });
}

function para(text, opts = {}) {
  return new Paragraph({
    children: [
      new TextRun({
        text,
        size: opts.size || 22,
        font: FONT,
        color: opts.color || DARK_GRAY,
        bold: opts.bold || false,
        italics: opts.italic || false,
      }),
    ],
    alignment: opts.align || AlignmentType.LEFT,
    spacing: { line: 336, before: opts.spaceBefore || 0, after: opts.spaceAfter || 120 },
  });
}

function buildCL(spec) {
  const {
    personal,
    subject_line,
    greeting,
    body_paragraphs,
    sign_off,
    role_applied_for,
    company_name,
  } = spec;
  const design = spec.design_settings || {};
  const accents = { navy: "1F4E79", slate: "475569", teal: "0F766E", indigo: "4338CA", emerald: "047857", charcoal: "263238" };
  const fonts = { aptos: "Aptos", calibri: "Calibri", arial: "Arial", georgia: "Georgia" };
  const margins = { one_page: 720, two_page: 900, auto: 1080 };
  FONT = fonts[design.font_family] || FONT;
  HEADING_COLOR = accents[design.accent_color] || HEADING_COLOR;
  MARGIN_DXA = margins[design.page_target] || MARGIN_DXA;

  const children = [];

  // Name header
  children.push(
    new Paragraph({
      children: [
        new TextRun({
          text: personal.full_name || "Candidate Name",
          bold: true,
          size: 32,
          font: FONT,
          color: HEADING_COLOR,
        }),
      ],
      alignment: AlignmentType.CENTER,
      spacing: { after: 40 },
    })
  );

  // Contact
  const contactParts = [personal.email, personal.phone, personal.location, personal.linkedin]
    .filter(Boolean);
  children.push(
    new Paragraph({
      children: [new TextRun({ text: contactParts.join("  |  "), size: 18, font: FONT, color: "666666" })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 40 },
    })
  );

  children.push(hr());

  // Date (right-aligned)
  children.push(
    new Paragraph({
      children: [
        new TextRun({
          text: new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }),
          size: 20,
          font: FONT,
          color: "888888",
        }),
      ],
      alignment: AlignmentType.RIGHT,
      spacing: { before: 80, after: 160 },
    })
  );

  // Subject line
  if (subject_line) {
    children.push(para(`Re: ${subject_line}`, { bold: true, color: HEADING_COLOR, spaceAfter: 160 }));
  }

  // Greeting
  children.push(para(greeting, { spaceAfter: 120 }));

  // Body paragraphs
  for (const bodyPara of (body_paragraphs || [])) {
    children.push(para(bodyPara, { spaceAfter: 120 }));
  }

  // Sign-off
  children.push(para(sign_off, { spaceBefore: 160, spaceAfter: 80 }));
  children.push(para(personal.full_name || "", { bold: true, spaceAfter: 40 }));

  if (personal.phone) children.push(para(personal.phone, { color: "666666", size: 19 }));
  if (personal.email) children.push(para(personal.email, { color: "666666", size: 19 }));

  // Footer
  const footer = new Footer({
    children: [
      new Paragraph({
        children: [
          new TextRun({
            text: `${personal.full_name || ""} — Cover Letter for ${role_applied_for || ""} at ${company_name || ""}`,
            size: 16,
            font: FONT,
            color: "999999",
          }),
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
            margin: { top: MARGIN_DXA, right: MARGIN_DXA, bottom: MARGIN_DXA, left: MARGIN_DXA },
          },
        },
        footers: { default: footer },
        children,
      },
    ],
  });
}

async function main() {
  const [,, specPath, outPath] = process.argv;
  if (!specPath || !outPath) {
    console.error("Usage: node generate_cl_docx.js <spec.json> <output.docx>");
    process.exit(1);
  }

  const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
  const doc = buildCL(spec);
  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outPath, buffer);
  console.log(`Cover letter written to ${outPath} (${buffer.length} bytes)`);
}

main().catch((err) => {
  console.error("Error:", err.message);
  process.exit(1);
});
