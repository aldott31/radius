/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";

export class DynamicDropdownField extends CharField {
    static template = "asr_olt_telnet.DynamicDropdownField";

    static extractProps(fieldInfo, dynamicInfo = {}) {
        // mos i jep undefined charField.extractProps
        const props = charField.extractProps(fieldInfo, dynamicInfo || {});

        // sigurohu që options nga XML të kalojnë (disa versione i kanë te fieldInfo.options)
        const xmlOptions = fieldInfo?.options || fieldInfo?.attrs?.options || {};
        if (xmlOptions && typeof xmlOptions === "object") {
            props.options = { ...(props.options || {}), ...xmlOptions };
        }
        return props;
    }

    get options() {
        try {
            // snake_case + camelCase + fallback automatik
            const fallbackName = `${this.props.name}_options`;
            const optionsFieldName =
                this.props.options?.options_field ||
                this.props.options?.optionsField ||
                fallbackName;

            const raw = this.props.record?.data?.[optionsFieldName];
            if (!raw) return [];

            const parsed = (typeof raw === "string") ? JSON.parse(raw) : raw;
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            console.error("[DynamicDropdown] options parse error:", e);
            return [];
        }
    }

    onSelect(ev) {
    const value = ev.target.value || false;

    // Odoo version-dependent: sometimes update isn't injected
    if (typeof this.props.update === "function") {
        this.props.update(value);
        return;
    }

    // Works across versions
    if (this.props.record && typeof this.props.record.update === "function") {
        this.props.record.update({ [this.props.name]: value });
        return;
    }

    console.error("[DynamicDropdown] No update method found", this.props);
}

}

registry.category("fields").add("dynamic_dropdown", {
    ...charField,
    component: DynamicDropdownField,
    extractProps: DynamicDropdownField.extractProps,
});
