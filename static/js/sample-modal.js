    (function () {
        "use strict";


        /*
        * ---------------------------------------------------------
        * Close modal
        * ---------------------------------------------------------
        */

        function closeModal() {
            var modalHost = document.getElementById("modal-host");

            if (modalHost) {
                modalHost.innerHTML = "";
            }
        }


        /*
        * ---------------------------------------------------------
        * Initialize modal
        * ---------------------------------------------------------
        */

        function initSampleModal() {

            var modalOverlay =
                document.getElementById("modal-overlay");

            /*
            * Modal is not currently present.
            *
            * This is normal because HTMX inserts the modal
            * dynamically.
            */
            if (!modalOverlay) {
                return;
            }


            /*
            * -----------------------------------------------------
            * Close buttons
            * -----------------------------------------------------
            */

            var closeButton =
                document.getElementById("modal-close");

            var cancelButton =
                document.getElementById("modal-cancel");


            if (closeButton) {
                closeButton.addEventListener(
                    "click",
                    closeModal
                );
            }


            if (cancelButton) {
                cancelButton.addEventListener(
                    "click",
                    closeModal
                );
            }


            /*
            * -----------------------------------------------------
            * Client phone controls
            * -----------------------------------------------------
            */

            var phoneField =
                document.getElementById("id_client_phone");

            var phoneMirror =
                document.getElementById(
                    "id_client_phone_mirror"
                );

            var togglePhoneButton =
                document.getElementById(
                    "btn-toggle-phone"
                );

            var clientNameField =
                document.getElementById(
                    "id_client_name"
                );

            var phoneHint =
                document.getElementById(
                    "phone-hint"
                );

            var phoneLabel =
                document.getElementById(
                    "phone-label"
                );


            if (
                togglePhoneButton &&
                phoneField
            ) {

                togglePhoneButton.addEventListener(
                    "click",
                    function () {

                        /*
                        * Enable phone for a new client
                        */
                        if (phoneField.disabled) {

                            phoneField.disabled = false;

                            phoneField.focus();


                            if (phoneHint) {
                                phoneHint.textContent =
                                    "Enter phone for new client.";
                            }


                            if (phoneLabel) {
                                phoneLabel.classList.add(
                                    "form-label--required"
                                );
                            }


                            /*
                            * Clear selected existing client.
                            */
                            if (clientNameField) {
                                clientNameField.value = "";
                            }

                        }

                        /*
                        * Disable phone and return to
                        * existing-client mode.
                        */
                        else {

                            phoneField.disabled = true;

                            phoneField.value = "";


                            if (phoneMirror) {
                                phoneMirror.value = "";
                            }


                            if (phoneHint) {
                                phoneHint.textContent =
                                    "Click + to unlock for a new client.";
                            }


                            if (phoneLabel) {
                                phoneLabel.classList.remove(
                                    "form-label--required"
                                );
                            }

                        }

                    }
                );


                /*
                * Keep hidden mirror synchronized.
                */
                phoneField.addEventListener(
                    "input",
                    function () {

                        if (phoneMirror) {
                            phoneMirror.value =
                                phoneField.value;
                        }

                    }
                );

            }


            /*
            * -----------------------------------------------------
            * Product Type cascade
            *
            * Category -> Product Type
            * -----------------------------------------------------
            */

            function unlockProductType() {

                var typeText =
                    document.getElementById(
                        "id_product_type__text"
                    );

                var typePk =
                    document.getElementById(
                        "id_product_type"
                    );

                var typeHint =
                    document.getElementById(
                        "type-hint"
                    );

                var categoryText =
                    document.getElementById(
                        "id_product_category__text"
                    );

                var categoryPk =
                    document.getElementById(
                        "id_product_category"
                    );


                var categoryValue = "";


                if (
                    categoryText &&
                    categoryText.value.trim()
                ) {
                    categoryValue =
                        categoryText.value.trim();
                }

                else if (
                    categoryPk &&
                    categoryPk.value.trim()
                ) {
                    categoryValue =
                        categoryPk.value.trim();
                }


                /*
                * Category exists.
                */
                if (categoryValue) {

                    if (typeText) {
                        typeText.disabled = false;
                    }


                    if (typeHint) {
                        typeHint.textContent =
                            "Select or type a product type.";
                    }

                }

                /*
                * No category.
                */
                else {

                    if (typeText) {
                        typeText.disabled = true;
                        typeText.value = "";
                    }


                    if (typePk) {
                        typePk.value = "";
                    }


                    if (typeHint) {
                        typeHint.textContent =
                            "Select category first.";
                    }

                }

            }


            var categoryTextElement =
                document.getElementById(
                    "id_product_category__text"
                );

            var categoryPkElement =
                document.getElementById(
                    "id_product_category"
                );


            if (categoryTextElement) {

                categoryTextElement.addEventListener(
                    "input",
                    unlockProductType
                );

            }


            if (categoryPkElement) {

                categoryPkElement.addEventListener(
                    "change",
                    unlockProductType
                );

            }


            unlockProductType();


            /*
            * -----------------------------------------------------
            * Requested Test cascade
            *
            * Molecular Type -> Requested Test
            * -----------------------------------------------------
            */

            function unlockRequestedTest() {

                var molecularType =
                    document.getElementById(
                        "id_molecular_type"
                    );

                var testText =
                    document.getElementById(
                        "id_requested_test__text"
                    );

                var testPk =
                    document.getElementById(
                        "id_requested_test"
                    );

                var testHint =
                    document.getElementById(
                        "test-hint"
                    );


                /*
                * Molecular type selected.
                */
                if (
                    molecularType &&
                    molecularType.value
                ) {

                    if (testText) {
                        testText.disabled = false;
                    }


                    if (testHint) {

                        var labels = {

                            "DNA_EXTRACTION":
                                "Select a DNA extraction method (e.g., Spin Column, Magnetic Bead).",

                            "PCR_QPCR":
                                "Select a PCR/qPCR method (e.g., Real-Time qPCR, End-point PCR).",

                            "SEQUENCING":
                                "Select a sequencing method (e.g., Sanger, 16S rRNA, WGS)."

                        };


                        testHint.textContent =
                            labels[molecularType.value] ||
                            "Select a test method.";

                    }

                }

                /*
                * No molecular type selected.
                */
                else {

                    if (testText) {
                        testText.disabled = true;
                        testText.value = "";
                    }


                    if (testPk) {
                        testPk.value = "";
                    }


                    if (testHint) {
                        testHint.textContent =
                            "Select molecular type first.";
                    }

                }

            }


            var molecularTypeElement =
                document.getElementById(
                    "id_molecular_type"
                );


            if (molecularTypeElement) {

                molecularTypeElement.addEventListener(
                    "change",
                    unlockRequestedTest
                );

            }


            unlockRequestedTest();

        }


        /*
        * ---------------------------------------------------------
        * HTMX request configuration
        *
        * Adds:
        *
        * category=<category>
        *
        * and
        *
        * molecular_type=<type>
        *
        * to SmartSelect requests.
        * ---------------------------------------------------------
        */

        function configureHtmxRequest(event) {

            var element =
                event.detail.elt;


            if (
                !element ||
                !element.id
            ) {
                return;
            }


            /*
            * Category
            */
            var categoryText =
                document.getElementById(
                    "id_product_category__text"
                );


            var categoryValue =
                categoryText
                    ? (categoryText.value || "").trim()
                    : "";


            if (
                categoryValue &&
                (
                    element.id ===
                        "id_product_type__text" ||

                    element.id ===
                        "id_requested_test__text"
                )
            ) {

                event.detail.parameters[
                    "category"
                ] = categoryValue;

            }


            /*
            * Molecular type
            */
            var molecularType =
                document.getElementById(
                    "id_molecular_type"
                );


            var molecularValue =
                molecularType
                    ? molecularType.value
                    : "";


            if (
                molecularValue &&
                element.id ===
                    "id_requested_test__text"
            ) {

                event.detail.parameters[
                    "molecular_type"
                ] = molecularValue;

            }

        }


        /*
        * ---------------------------------------------------------
        * Register global HTMX listener ONCE
        * ---------------------------------------------------------
        */

        document.body.addEventListener(
            "htmx:configRequest",
            configureHtmxRequest
        );


        /*
        * ---------------------------------------------------------
        * Initialize when the page initially loads
        * ---------------------------------------------------------
        */

        if (
            document.readyState ===
            "loading"
        ) {

            document.addEventListener(
                "DOMContentLoaded",
                initSampleModal
            );

        }

        else {

            initSampleModal();

        }


        /*
        * ---------------------------------------------------------
        * Initialize after HTMX swaps content.
        *
        * This is important because the modal is inserted
        * dynamically into #modal-host.
        * ---------------------------------------------------------
        */

        document.body.addEventListener(
            "htmx:afterSwap",
            function (event) {

                var modalHost =
                    document.getElementById(
                        "modal-host"
                    );


                if (!modalHost) {
                    return;
                }


                /*
                * Only initialize if the swap happened
                * inside the modal host.
                */
                if (
                    event.target === modalHost ||
                    modalHost.contains(event.target)
                ) {

                    initSampleModal();

                }

            }
        );

    })();
