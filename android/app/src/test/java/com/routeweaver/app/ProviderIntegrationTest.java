package com.routeweaver.app;

import org.junit.Test;

import java.util.Set;

import static org.junit.Assert.assertTrue;

public class ProviderIntegrationTest {
    @Test public void ruleSummaryContainsModeAppsAndDomains() {
        String summary = ProviderIntegration.ruleSummary(
                RoutePolicy.Mode.REVERSE,
                Set.of("com.example.domestic"),
                Set.of("example.cn")
        );
        assertTrue(summary.contains("反向隔离"));
        assertTrue(summary.contains("com.example.domestic"));
        assertTrue(summary.contains("example.cn"));
    }
}

