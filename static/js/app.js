document.addEventListener('DOMContentLoaded', function () {
  // Previsualización múltiple de imágenes en Galería de Alojamiento
  const inputGaleria = document.getElementById('inputGaleria');
  const previewContainer = document.getElementById('previewGaleria');
  const dropzone = document.getElementById('dropzoneGaleria');

  function renderizarPreviews(files) {
    if (!previewContainer) return;
    previewContainer.innerHTML = '';
    Array.from(files).forEach((file) => {
      if (!file.type.startsWith('image/')) return;
      const reader = new FileReader();
      reader.onload = function (e) {
        const div = document.createElement('div');
        div.className = 'preview-item';
        div.innerHTML = `<img src="${e.target.result}" alt="${file.name}" title="${file.name}">`;
        previewContainer.appendChild(div);
      };
      reader.readAsDataURL(file);
    });
  }

  if (inputGaleria) {
    inputGaleria.addEventListener('change', function () {
      renderizarPreviews(this.files);
    });
  }

  if (dropzone && inputGaleria) {
    dropzone.addEventListener('click', () => inputGaleria.click());
    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.style.borderColor = '#0c5a62';
    });
    dropzone.addEventListener('dragleave', () => {
      dropzone.style.borderColor = '#b8c4c2';
    });
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.style.borderColor = '#b8c4c2';
      if (e.dataTransfer.files.length) {
        inputGaleria.files = e.dataTransfer.files;
        renderizarPreviews(e.dataTransfer.files);
      }
    });
  }

  // =========================================================================
  // CALENDARIO EN RANGO (DÍAS APARTADOS TACHADOS) Y CÁLCULO DE TOTAL POR NOCHES
  // =========================================================================
  const detalleContainer = document.getElementById('detalleAlojamientoContainer');
  if (detalleContainer && typeof flatpickr !== 'undefined') {
    let fechasOcupadasPorHab = {};
    try {
      fechasOcupadasPorHab = JSON.parse(detalleContainer.getAttribute('data-fechas-ocupadas') || '{}');
    } catch (e) {
      fechasOcupadasPorHab = {};
    }
    const todosApartados = [...new Set(Object.values(fechasOcupadasPorHab).flat())];

    function formatearCOP(valor) {
      return '$' + Math.round(valor).toLocaleString('es-CO');
    }

    function fechaLocalIso(dateObj) {
      const y = dateObj.getFullYear();
      const m = String(dateObj.getMonth() + 1).padStart(2, '0');
      const d = String(dateObj.getDate()).padStart(2, '0');
      return `${y}-${m}-${d}`;
    }

    function iniciarCalendarioRango(inputVisible, inputEntrada, inputSalida, fechasBloqueadas, alCambiar) {
      if (!inputVisible) return null;

      const defaultDates = [];
      if (inputEntrada && inputEntrada.value) defaultDates.push(inputEntrada.value);
      if (inputSalida && inputSalida.value) defaultDates.push(inputSalida.value);

      const fp = flatpickr(inputVisible, {
        mode: 'range',
        locale: 'es',
        dateFormat: 'Y-m-d',
        minDate: 'today',
        defaultDate: defaultDates.length === 2 ? defaultDates : undefined,
        disable: fechasBloqueadas,
        onDayCreate: function (dObj, dStr, instance, dayElem) {
          const fechaIso = fechaLocalIso(dayElem.dateObj);
          if (fechasBloqueadas.includes(fechaIso)) {
            dayElem.classList.add('dia-apartado');
            dayElem.title = 'Día apartado / no disponible';
          }
        },
        onChange: function (selectedDates) {
          if (selectedDates.length === 2) {
            const f1 = fechaLocalIso(selectedDates[0]);
            const f2 = fechaLocalIso(selectedDates[1]);
            if (inputEntrada) inputEntrada.value = f1;
            if (inputSalida) inputSalida.value = f2;
            if (typeof alCambiar === 'function') alCambiar(selectedDates[0], selectedDates[1]);
          } else {
            if (inputEntrada) inputEntrada.value = '';
            if (inputSalida) inputSalida.value = '';
            if (typeof alCambiar === 'function') alCambiar(null, null);
          }
        }
      });

      if (defaultDates.length === 2 && typeof alCambiar === 'function') {
        alCambiar(new Date(defaultDates[0] + 'T00:00:00'), new Date(defaultDates[1] + 'T00:00:00'));
      }

      return fp;
    }

    // 1. Calendario principal de búsqueda
    const formFiltro = detalleContainer.querySelector('form[method="get"]');
    const filtroEntrada = formFiltro ? formFiltro.querySelector('input[name="fecha_entrada"]') : null;
    const filtroSalida = formFiltro ? formFiltro.querySelector('input[name="fecha_salida"]') : null;

    if (formFiltro) {
      iniciarCalendarioRango(
        formFiltro.querySelector('#rangoFechasFiltro'),
        filtroEntrada,
        filtroSalida,
        todosApartados,
        function () {
          document.querySelectorAll('[id^="modalReservar"]').forEach(sincronizarModal);
        }
      );
    }

    // 2. Sincronizar fechas del filtro superior en cada modal (solo lectura, sin editar)
    function sincronizarModal(modal) {
      if (!modal) return;
      const precioNoche = parseFloat((modal.getAttribute('data-precio-noche') || '0').replace(',', '.'));
      const inputTexto = modal.querySelector('.rango-fechas-modal');
      const hiddenEntrada = modal.querySelector('input[name="fecha_entrada"]');
      const hiddenSalida = modal.querySelector('input[name="fecha_salida"]');
      const resumenBox = modal.querySelector('.resumen-precio-modal');
      const btnConfirmar = modal.querySelector('.btn-confirmar-reserva');

      const f1 = (filtroEntrada && filtroEntrada.value) || (hiddenEntrada && hiddenEntrada.value) || '';
      const f2 = (filtroSalida && filtroSalida.value) || (hiddenSalida && hiddenSalida.value) || '';

      if (hiddenEntrada) hiddenEntrada.value = f1;
      if (hiddenSalida) hiddenSalida.value = f2;

      if (f1 && f2) {
        if (inputTexto) inputTexto.value = `${f1}  a  ${f2}`;
        const dIn = new Date(f1 + 'T00:00:00');
        const dOut = new Date(f2 + 'T00:00:00');
        const noches = Math.round((dOut - dIn) / (1000 * 60 * 60 * 24));
        if (noches > 0) {
          const total = noches * precioNoche;
          if (resumenBox) {
            resumenBox.innerHTML = `<span class="text-success">Estadía de ${noches} noche(s) × ${formatearCOP(precioNoche)} = <strong>Total: ${formatearCOP(total)}</strong></span>`;
          }
          if (btnConfirmar) btnConfirmar.disabled = false;
        } else {
          if (resumenBox) {
            resumenBox.innerHTML = `<span class="text-danger">La fecha de salida debe ser posterior a la de entrada.</span>`;
          }
          if (btnConfirmar) btnConfirmar.disabled = true;
        }
      } else {
        if (inputTexto) inputTexto.value = '';
        if (resumenBox) {
          resumenBox.innerHTML = `<span class="text-warning text-dark">Primero selecciona entrada y salida en el calendario superior.</span>`;
        }
        if (btnConfirmar) btnConfirmar.disabled = true;
      }
    }

    document.querySelectorAll('[id^="modalReservar"]').forEach((modal) => {
      sincronizarModal(modal);
      modal.addEventListener('show.bs.modal', function () {
        sincronizarModal(modal);
      });
    });
  }

  // Actualizar coordenadas automáticamente al cambiar Municipio en el formulario de Alojamiento
  const selectMunicipio = document.getElementById('selectMunicipio');
  const inputLat = document.getElementById('inputLatitud');
  const inputLng = document.getElementById('inputLongitud');

  if (selectMunicipio && inputLat && inputLng) {
    selectMunicipio.addEventListener('change', function () {
      const opt = this.options[this.selectedIndex];
      const lat = opt.getAttribute('data-lat');
      const lng = opt.getAttribute('data-lng');
      if (lat && lng) {
        inputLat.value = lat.replace(',', '.');
        inputLng.value = lng.replace(',', '.');
        if (window.actualizarMarcadorMapa) {
          window.actualizarMarcadorMapa(parseFloat(inputLat.value), parseFloat(inputLng.value));
        }
      }
    });
  }
});
