package com.cymatic.client.input

import org.junit.Assert.*
import org.junit.Test

class ControllerIdentityTest {

    @Test
    fun `same address matches case-insensitively`() {
        assertTrue(ControllerIdentity.sameDevice("AA:BB:CC:DD:EE:FF", "aa:bb:cc:dd:ee:ff"))
        assertFalse(ControllerIdentity.sameDevice("AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"))
    }

    @Test
    fun `blank addresses never match`() {
        assertFalse(ControllerIdentity.sameDevice(null, "AA:BB:CC:DD:EE:FF"))
        assertFalse(ControllerIdentity.sameDevice("AA:BB:CC:DD:EE:FF", null))
        assertFalse(ControllerIdentity.sameDevice("", ""))
        assertFalse(ControllerIdentity.sameDevice(null, null))
    }

    @Test
    fun `known controller names match`() {
        assertTrue(ControllerIdentity.isAllowedControllerName("Oculus Quest 2"))
        assertTrue(ControllerIdentity.isAllowedControllerName("Daydream Controller"))
        assertTrue(ControllerIdentity.isAllowedControllerName("Pico 4"))
        assertTrue(ControllerIdentity.isAllowedControllerName("Gear VR Controller"))
        assertTrue(ControllerIdentity.isAllowedControllerName("My Controller Pro"))
    }

    @Test
    fun `lookalike non-controller names rejected`() {
        // Old substring "vr" check matched these.
        assertFalse(ControllerIdentity.isAllowedControllerName("AVR-X2200 Speaker"))
        assertFalse(ControllerIdentity.isAllowedControllerName("BRAVIA TV"))
        assertFalse(ControllerIdentity.isAllowedControllerName("JBL Speaker"))
        assertFalse(ControllerIdentity.isAllowedControllerName(null))
        assertFalse(ControllerIdentity.isAllowedControllerName("  "))
    }

    @Test
    fun `claim label tolerates blanks`() {
        assertEquals(
            "name=<unnamed> address=<no-address>",
            ControllerIdentity.claimLabel(null, null)
        )
        assertEquals(
            "name=Oculus Quest address=AA:BB:CC:DD:EE:FF",
            ControllerIdentity.claimLabel("Oculus Quest", "AA:BB:CC:DD:EE:FF")
        )
    }
}
