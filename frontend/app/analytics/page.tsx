"use client";

import { useI18n } from "@/lib/i18n";
import { PageHeader, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui";
import { SensitivityTab, UncertaintyTab } from "@/components/analytics/UncertaintySensitivity";
import { BayesTab, LsqTab, ValidationTab } from "@/components/analytics/CalibrationValidation";

export default function AnalyticsPage() {
  const { t } = useI18n();
  return (
    <div className="space-y-4">
      <PageHeader title={t("analytics.title")} subtitle={t("app.boundary")} />
      <Tabs defaultValue="uq">
        <TabsList>
          {(["uq", "sa", "lsq", "bayes", "validation"] as const).map((k) => <TabsTrigger key={k} value={k}>{t(`analytics.tabs.${k}`)}</TabsTrigger>)}
        </TabsList>
        <div className="pt-4">
          <TabsContent value="uq"><UncertaintyTab /></TabsContent>
          <TabsContent value="sa"><SensitivityTab /></TabsContent>
          <TabsContent value="lsq"><LsqTab /></TabsContent>
          <TabsContent value="bayes"><BayesTab /></TabsContent>
          <TabsContent value="validation"><ValidationTab /></TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
