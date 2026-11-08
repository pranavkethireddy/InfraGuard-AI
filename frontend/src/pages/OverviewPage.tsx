import { useQuery } from "@tanstack/react-query";
import { assetsQuery, incidentsQuery, modelsQuery, readingsQuery } from "@/api/queries";
import { ReadingsChart } from "@/components/ReadingsChart";
import { EquipmentTable, IncidentQueue } from "@/components/tables";
import { Empty, ErrorState, Loading, Mono, PageHeader, Section, dt } from "@/components/ui-kit";
import { AppLink } from "@/lib/router-adapter";

export function OverviewPage() {
  const assets = useQuery(assetsQuery());
  const open = useQuery(incidentsQuery("open"));
  const models = useQuery(modelsQuery());
  const trendAsset = assets.data?.items.find((a) => a.compatible_detector === "cooling-rule-v1");
  const readings = useQuery({ ...readingsQuery(trendAsset?.asset_id ?? ""), enabled: !!trendAsset });
  const detector = models.data?.items.find((m) => m.detector_id === trendAsset?.compatible_detector);
  const threshold = detector?.rule_config?.temperature_threshold_c ?? null;

  return (
    <>
      <PageHeader title="Overview"
        meta={assets.data ? <>{assets.data.total} assets · {open.data ? `${open.data.total} open incidents` : "incidents loading"}</> : "Loading"} />
      <div className="space-y-6">
        <div className="grid gap-6 xl:grid-cols-[minmax(0,2.3fr)_minmax(0,1fr)]">
          <Section title={trendAsset ? `Supply temperature — ${trendAsset.name}` : "Sensor trend"}
            aside={readings.data && <Mono>{readings.data.total} readings</Mono>}>
            {!trendAsset ? <Empty>No asset with a cooling detector.</Empty>
              : readings.isLoading ? <Loading /> : readings.error ? <ErrorState error={readings.error} />
              : readings.data?.items.length ? <ReadingsChart readings={readings.data.items} threshold={threshold} height={330} />
              : <Empty>No readings in the returned window.</Empty>}
          </Section>
          <Section title="Open incident queue" aside={<AppLink to="/incidents" className="text-primary underline underline-offset-2">All incidents</AppLink>} flush>
            {open.isLoading ? <Loading /> : open.error ? <div className="p-3"><ErrorState error={open.error} /></div>
              : !open.data?.items.length ? <Empty>No open incidents.</Empty> : <IncidentQueue incidents={open.data.items} compact />}
          </Section>
        </div>
        <Section title="Equipment" aside={<AppLink to="/assets" className="text-primary underline underline-offset-2">All assets</AppLink>} flush>
          {assets.isLoading ? <Loading /> : assets.error ? <div className="p-3"><ErrorState error={assets.error} /></div>
            : !assets.data?.items.length ? <Empty>No assets registered.</Empty> : <EquipmentTable assets={assets.data.items} />}
        </Section>
      </div>
    </>
  );
}
