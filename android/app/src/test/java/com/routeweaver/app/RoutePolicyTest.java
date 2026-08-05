package com.routeweaver.app;

import org.junit.Test;
import java.util.Set;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

public class RoutePolicyTest {
    @Test public void forwardOnlyMatchesUseVpn() {
        assertEquals(RoutePolicy.Target.VPN, RoutePolicy.decide(RoutePolicy.Mode.FORWARD, "com.browser", "mail.google.com", Set.of(), Set.of("google.com")));
        assertEquals(RoutePolicy.Target.DIRECT, RoutePolicy.decide(RoutePolicy.Mode.FORWARD, "com.browser", "baidu.com", Set.of(), Set.of("google.com")));
    }

    @Test public void reverseMatchesBypassVpn() {
        assertEquals(RoutePolicy.Target.DIRECT, RoutePolicy.decide(RoutePolicy.Mode.REVERSE, "com.weixin", "example.com", Set.of("com.weixin"), Set.of()));
        assertEquals(RoutePolicy.Target.VPN, RoutePolicy.decide(RoutePolicy.Mode.REVERSE, "com.browser", "example.com", Set.of("com.weixin"), Set.of()));
    }

    @Test public void wildcardAndUnicodeDomain() {
        assertTrue(RoutePolicy.matchesDomain("子.例子.测试", Set.of("*.例子.测试")));
    }
}

