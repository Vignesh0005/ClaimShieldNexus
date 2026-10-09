// Loaded on demand from BriefViewer so @react-pdf/renderer stays out of the main bundle.
import { Document, Page, StyleSheet, Text, View, pdf } from "@react-pdf/renderer";
import type { Brief } from "@/lib/types";
import { inr, score } from "@/lib/utils";

const s = StyleSheet.create({
  page: { padding: 40, fontSize: 10, fontFamily: "Helvetica", color: "#0F172A", lineHeight: 1.45 },
  banner: { backgroundColor: "#FEF3C7", padding: 6, marginBottom: 14, fontSize: 9, textAlign: "center" },
  title: { fontSize: 16, fontFamily: "Helvetica-Bold", marginBottom: 2 },
  sub: { color: "#475569", marginBottom: 12 },
  h: { fontSize: 11, fontFamily: "Helvetica-Bold", marginTop: 12, marginBottom: 4, borderBottom: "1 solid #CBD5E1", paddingBottom: 2 },
  row: { flexDirection: "row", marginBottom: 2 },
  k: { width: 130, color: "#475569" },
  li: { marginBottom: 2 },
  footer: { position: "absolute", bottom: 24, left: 40, right: 40, fontSize: 8, color: "#475569", textAlign: "center" },
});

function BriefDocument({ brief }: { brief: Brief }) {
  const facts: [string, string][] = [
    ["Provider", brief.provider],
    ["Risk score", brief.riskLine],
    ["Potential amount (INR)", inr(brief.amount).replace("₹", "INR ")],
    ["Members affected", String(brief.members)],
    ["Member harm score", brief.harmLine],
    ["Confidence", score(brief.confidence)],
  ];
  const list = (items: string[], numbered = false) =>
    items.map((t, i) => (
      <Text key={i} style={s.li}>
        {numbered ? `${i + 1}. ` : "- "}
        {t.replaceAll("₹", "INR ")}
      </Text>
    ));
  return (
    <Document title={`SIU investigation brief ${brief.caseId}`}>
      <Page size="A4" style={s.page}>
        <Text style={s.banner}>{brief.disclaimer}</Text>
        <Text style={s.title}>SIU investigation brief: {brief.caseId}</Text>
        <Text style={s.sub}>
          {brief.type === "technical" ? "Technical version" : "Plain-language version"}, generated {brief.generatedAt.slice(0, 16).replace("T", " ")} UTC
        </Text>
        {facts.map(([k, v]) => (
          <View key={k} style={s.row}>
            <Text style={s.k}>{k}</Text>
            <Text>{v}</Text>
          </View>
        ))}
        <Text style={s.h}>Evidence</Text>
        {list(brief.evidence, true)}
        <Text style={s.h}>Timeline</Text>
        {list(brief.timeline)}
        <Text style={s.h}>Network context</Text>
        <Text>{brief.network.text}</Text>
        <Text style={s.h}>Limitations</Text>
        {list(brief.limitations)}
        <Text style={s.h}>Recommended action</Text>
        <Text>{brief.recommendedAction}</Text>
        <Text style={s.footer} fixed>
          {brief.disclaimer} Prepared for human review. ClaimShield Nexus.
        </Text>
      </Page>
    </Document>
  );
}

export async function downloadBriefPdf(brief: Brief) {
  const blob = await pdf(<BriefDocument brief={brief} />).toBlob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${brief.caseId}-brief-${brief.type}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}
